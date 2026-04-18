import logging
import re
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml
from ambyte_cli.config import AmbyteConfig
from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	PrivacyEnhancementRule,
	PrivacyMethod,
	PurposeRestriction,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)
T = TypeVar('T', bound=Enum)


class PolicyLoaderError(Exception):
	"""Raised when a policy file cannot be parsed."""

	def __init__(self, message: str, file_path: Path | str | None = None):
		self.message = message
		self.file_path = file_path
		super().__init__(self.message)


class ObligationLoader:
	def __init__(self, config: AmbyteConfig):
		self.policy_dir = config.abs_policies_dir

	def validate_all(self) -> list[str]:
		"""
		Validation-Only Mode.
		Scans all files and returns a list of error messages.
		If the list is empty, the workspace is 'Push-Ready'.
		"""
		_, errors = self._load_batch()
		return errors

	def load_all(self) -> list[Obligation]:
		"""
		Loads all valid obligations.
		Note: This is permissive and skips broken files (logged as warnings).
		For strict loading, use validate_all() first.
		"""
		valid_obs, _ = self._load_batch()
		return valid_obs

	def _load_batch(self) -> tuple[list[Obligation], list[str]]:
		"""
		Internal logic to crawl the directory and parse all YAML files.
		Returns a tuple of (list of valid Obligations, list of Error Strings).
		"""
		obligations: list[Obligation] = []
		errors: list[str] = []

		if not self.policy_dir.exists():
			return [], [f'Policy directory not found: {self.policy_dir}']

		# Support recursive globbing for nested policy structures
		files = list(self.policy_dir.glob('**/*.yaml')) + list(self.policy_dir.glob('**/*.yml'))

		for file_path in files:
			try:
				ob = self._load_file(file_path)
				obligations.append(ob)
			except PolicyLoaderError as e:
				err_msg = f'File {file_path.relative_to(self.policy_dir)}: {e.message}'
				errors.append(err_msg)
			except Exception as e:
				err_msg = f'File {file_path.relative_to(self.policy_dir)}: Unexpected crash - {str(e)}'
				errors.append(err_msg)

		return obligations, errors

	def _load_file(self, path: Path) -> Obligation:
		"""Reads file from disk and parses it."""
		try:
			with open(path, encoding='utf-8') as f:
				raw = yaml.safe_load(f)
		except yaml.YAMLError as e:
			raise PolicyLoaderError(f'Invalid YAML syntax: {e}', file_path=path) from None
		except Exception as e:
			raise PolicyLoaderError(f'Could not read file: {e}', file_path=path) from None

		return self.parse_obligation_data(raw, source_name=path.name)

	def parse_obligation_data(self, raw: dict[str, Any], source_name: str = 'Unknown') -> Obligation:
		"""
		Parses a raw dictionary into an Obligation object.
		"""
		if not raw:
			raise PolicyLoaderError(f'Policy definition in {source_name} is empty.')

		try:
			# 1. Parse Provenance
			provenance_data = raw.get('provenance', {})
			provenance = SourceProvenance(**provenance_data)

			# 2. Map Enums
			enf_level = self._resolve_enum(EnforcementLevel, raw.get('enforcement_level', 'AUDIT_ONLY'))

			# 3. Handle Polymorphic Constraint
			constraint_kwargs = {}

			# Direct root-level keys (Recommended style)
			if 'retention' in raw:
				constraint_kwargs = self._build_constraint_kwargs('RETENTION', raw['retention'])
			elif 'geofencing' in raw:
				constraint_kwargs = self._build_constraint_kwargs('GEOFENCING', raw['geofencing'])
			elif 'purpose' in raw:
				constraint_kwargs = self._build_constraint_kwargs('PURPOSE_RESTRICTION', raw['purpose'])
			elif 'privacy' in raw:
				constraint_kwargs = self._build_constraint_kwargs('PRIVACY_ENHANCEMENT', raw['privacy'])
			elif 'ai_model' in raw:
				constraint_kwargs = self._build_constraint_kwargs('AI_MODEL_CONSTRAINT', raw['ai_model'])
			# Fallback for nested 'constraint' block
			elif 'constraint' in raw:
				c_data = raw['constraint']
				c_type = c_data.get('type', '').upper()
				constraint_kwargs = self._build_constraint_kwargs(c_type, c_data)
			else:
				raise PolicyLoaderError('Policy is missing a valid constraint (retention, geofencing, etc.)')

			# 4. Construct Final Object
			return Obligation(
				id=cast(str, raw.get('id')),
				title=cast(str, raw.get('title')),
				description=str(raw.get('description', '')),
				provenance=provenance,
				enforcement_level=enf_level,
				target=raw.get('target', {}),
				**constraint_kwargs,
			)

		except ValidationError as e:
			# Create a readable summary of Pydantic validation errors
			error_details = []
			for err in e.errors():
				loc = ' -> '.join(str(part) for part in err['loc'])
				error_details.append(f'[{loc}]: {err["msg"]}')

			raise PolicyLoaderError(f'Schema Validation Failed: {"; ".join(error_details)}') from None
		except ValueError as e:
			raise PolicyLoaderError(str(e)) from e

	def _build_constraint_kwargs(self, c_type: str, data: dict[str, Any]) -> dict[str, Any]:
		"""Maps YAML constraint blocks to Schema fields."""
		if not c_type:
			raise PolicyLoaderError("Constraint block missing 'type' field.")

		if c_type == 'RETENTION':
			dur_str = data.get('duration', '0d')
			duration = self._parse_duration(dur_str)
			trigger = self._resolve_enum(RetentionTrigger, data.get('trigger', 'UNSPECIFIED'))
			return {
				'retention': RetentionRule(
					duration=duration,
					trigger=trigger,
					allow_legal_hold_override=data.get('allow_legal_hold_override', False),
				)
			}

		if c_type == 'GEOFENCING':
			return {
				'geofencing': GeofencingRule(
					allowed_regions=data.get('allowed_regions', []),
					denied_regions=data.get('denied_regions', []),
					strict_residency=data.get('strict_residency', False),
				)
			}

		if c_type == 'PURPOSE_RESTRICTION':
			return {
				'purpose': PurposeRestriction(
					allowed_purposes=data.get('allowed_purposes', []), denied_purposes=data.get('denied_purposes', [])
				)
			}

		if c_type == 'PRIVACY_ENHANCEMENT':
			method = self._resolve_enum(PrivacyMethod, data.get('method', 'UNSPECIFIED'))
			return {'privacy': PrivacyEnhancementRule(method=method, parameters=data.get('parameters', {}))}

		if c_type == 'AI_MODEL_CONSTRAINT':
			return {
				'ai_model': AiModelConstraint(
					training_allowed=data.get('training_allowed', False),
					fine_tuning_allowed=data.get('fine_tuning_allowed', False),
					rag_usage_allowed=data.get('rag_usage_allowed', False),
					requires_open_source_release=data.get('requires_open_source_release', False),
					attribution_text_required=data.get('attribution_text_required', ''),
				)
			}

		raise PolicyLoaderError(f"Unknown constraint type: '{c_type}'")

	def _resolve_enum(self, enum_cls: type[T], value: str | int) -> T:
		"""Fuzzy enum resolution (handles case-insensitivity and short/long names)."""
		if isinstance(value, int):
			try:
				return enum_cls(value)
			except ValueError:
				pass

		norm_val = str(value).upper().strip()
		if norm_val in enum_cls.__members__:
			return enum_cls[norm_val]

		for member_name, member in enum_cls.__members__.items():
			if member_name.endswith(f'_{norm_val}') or norm_val.endswith(f'_{member_name}'):
				return member

		valid_options = list(enum_cls.__members__.keys())
		raise ValueError(f"Invalid value '{value}'. Valid options: {valid_options}")

	def _parse_duration(self, val: str) -> timedelta:
		"""Parses shorthand like '30d' or '1y' into timedelta."""
		match = re.match(r'^(\d+)([dmyh])$', str(val).lower())
		if not match:
			raise ValueError(f"Invalid duration format: '{val}'. Use '30d', '24h', etc.")

		amount, unit = int(match.group(1)), match.group(2)
		if unit == 'h':
			return timedelta(hours=amount)
		if unit == 'd':
			return timedelta(days=amount)
		if unit == 'm':
			return timedelta(days=amount * 30)
		if unit == 'y':
			return timedelta(days=amount * 365)
		return timedelta(days=0)

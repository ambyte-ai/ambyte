import re
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeVar

import yaml
from ambyte_cli.config import AmbyteConfig
from ambyte_cli.ui.console import console
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

T = TypeVar('T')


class PolicyLoaderError(Exception):
	"""Raised when a policy file cannot be parsed."""

	pass


class ObligationLoader:
	def __init__(self, config: AmbyteConfig):
		self.policy_dir = config.abs_policies_dir

	def load_all(self) -> list[Obligation]:
		"""
		Scans the configured policy directory for .yaml/.yml files
		and parses them into Obligation objects.
		"""
		obligations: list[Obligation] = []
		# Support both .yaml and .yml
		files = list(self.policy_dir.glob('**/*.yaml')) + list(self.policy_dir.glob('**/*.yml'))

		if not files:
			# We don't error here, just return empty, let caller decide if that's bad
			return []

		for file_path in files:
			try:
				ob = self._load_file(file_path)
				obligations.append(ob)
			except PolicyLoaderError as e:
				console.print(f'[bold red]Error loading {file_path.name}:[/bold red] {e}')
			except Exception as e:
				console.print(f'[bold red]Unexpected crash in {file_path.name}:[/bold red] {e}')

		return obligations

	def _load_file(self, path: Path) -> Obligation:
		"""Reads file from disk and parses it."""
		with open(path, encoding='utf-8') as f:
			try:
				raw = yaml.safe_load(f)
			except yaml.YAMLError as e:
				raise PolicyLoaderError(f'Invalid YAML syntax: {e}') from None

		return self.parse_obligation_data(raw, source_name=path.name)

	def parse_obligation_data(self, raw: dict[str, Any], source_name: str = 'Unknown') -> Obligation:
		"""
		Parses a raw dictionary into an Obligation object.
		Publicly accessible for Git/History loading.
		"""
		if not raw:
			raise PolicyLoaderError(f'Policy definition in {source_name} is empty.')

		try:
			# 1. Parse Provenance (Optional in Pydantic, but we enforce it for Audit)
			provenance = SourceProvenance(**raw.get('provenance', {}))

			# 2. Map Enums
			enf_level = self._resolve_enum(EnforcementLevel, raw.get('enforcement_level', 'AUDIT_ONLY'))

			# 3. Handle Polymorphic Constraint
			constraint_data = raw.get('constraint', {})
			constraint_type = constraint_data.get('type', '').upper()

			constraint_kwargs = self._build_constraint_kwargs(constraint_type, constraint_data)

			# 4. Construct Final Object
			return Obligation(
				id=str(raw.get('id')),
				title=str(raw.get('title')),
				description=str(raw.get('description', '')),
				provenance=provenance,
				enforcement_level=enf_level,
				**constraint_kwargs,
			)

		except ValidationError as e:
			# Simplify Pydantic errors
			errors = '; '.join([f'{err["loc"][0]}: {err["msg"]}' for err in e.errors()])
			raise PolicyLoaderError(f'Schema Validation Failed: {errors}') from None
		except ValueError as e:
			raise PolicyLoaderError(str(e)) from e

	def _build_constraint_kwargs(self, c_type: str, data: dict[str, Any]) -> dict[str, Any]:
		"""Maps YAML 'constraint' block to Schema OneOf fields."""
		if not c_type:
			raise PolicyLoaderError("Constraint block missing 'type' field.")

		if c_type == 'RETENTION':
			dur_str = data.get('duration', '0d')
			duration = self._parse_duration(dur_str)
			trigger = self._resolve_enum(RetentionTrigger, data.get('trigger', 'UNSPECIFIED'))

			rule = RetentionRule(
				duration=duration,
				trigger=trigger,
				allow_legal_hold_override=data.get('allow_legal_hold_override', False),
			)
			return {'retention': rule}

		if c_type == 'GEOFENCING':
			rule = GeofencingRule(
				allowed_regions=data.get('allowed_regions', []),
				denied_regions=data.get('denied_regions', []),
				strict_residency=data.get('strict_residency', False),
			)
			return {'geofencing': rule}

		if c_type == 'PURPOSE_RESTRICTION':
			rule = PurposeRestriction(
				allowed_purposes=data.get('allowed_purposes', []), denied_purposes=data.get('denied_purposes', [])
			)
			return {'purpose': rule}

		if c_type == 'PRIVACY_ENHANCEMENT':
			method = self._resolve_enum(PrivacyMethod, data.get('method', 'UNSPECIFIED'))
			rule = PrivacyEnhancementRule(method=method, parameters=data.get('parameters', {}))
			return {'privacy': rule}

		if c_type == 'AI_MODEL_CONSTRAINT':
			rule = AiModelConstraint(
				training_allowed=data.get('training_allowed', False),
				fine_tuning_allowed=data.get('fine_tuning_allowed', False),
				rag_usage_allowed=data.get('rag_usage_allowed', False),
				requires_open_source_release=data.get('requires_open_source_release', False),
				attribution_text_required=data.get('attribution_text_required', ''),
			)
			return {'ai_model': rule}

		raise PolicyLoaderError(f"Unknown constraint type: '{c_type}'")

	def _resolve_enum(self, enum_cls: type[T], value: str | int) -> T:
		if isinstance(value, int):
			try:
				return enum_cls(value)
			except ValueError:
				pass

		norm_val = str(value).upper().strip()

		# Exact match
		if norm_val in enum_cls.__members__:
			return enum_cls[norm_val]

		# Suffix match ("BLOCKING" -> "ENFORCEMENT_LEVEL_BLOCKING")
		for member_name, member in enum_cls.__members__.items():
			if member_name.endswith(f'_{norm_val}') or member_name == norm_val:
				return member

		valid_options = [m.split('_')[-1] for m in enum_cls.__members__.keys()]
		raise ValueError(f"Invalid value '{value}' for {enum_cls.__name__}. Valid options: {valid_options}")

	def _parse_duration(self, val: str) -> timedelta:
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

from datetime import date
from enum import Enum, StrEnum
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from ambyte_schemas.models.common import AmbyteBaseModel, RiskSeverity
from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	PrivacyMethod,
	RetentionTrigger,
)


class ConstraintType(StrEnum):
	"""
	Maps the 'type' field in YAML to the specific constraint block
	in the Obligation schema.
	"""

	RETENTION = 'RETENTION'
	GEOFENCING = 'GEOFENCING'
	PURPOSE_RESTRICTION = 'PURPOSE_RESTRICTION'
	PRIVACY_ENHANCEMENT = 'PRIVACY_ENHANCEMENT'
	AI_MODEL_CONSTRAINT = 'AI_MODEL_CONSTRAINT'


def validate_enum_by_name(enum_cls: type[Enum]):
	"""
	Returns a validator that converts a string name (e.g. "BLOCKING")
	into the Enum value (int). Handles prefix mismatches loosely.
	"""

	def _validate(v: Any) -> Any:
		if isinstance(v, int):
			return v
		if isinstance(v, str):
			v_upper = v.upper()
			# 1. Try exact name match
			try:
				return enum_cls[v].value
			except KeyError:
				pass

			# 2. Fuzzy matching
			for name, member in enum_cls.__members__.items():
				# Case A: Enum is Long, Input is Short
				# (e.g. Enum: ENFORCEMENT_LEVEL_BLOCKING, Input: BLOCKING)
				if name.endswith(f'_{v_upper}'):
					return member.value

				# Case B: Enum is Short, Input is Long
				# (e.g. Enum: HIGH, Input: RISK_SEVERITY_HIGH)
				if v_upper.endswith(f'_{name}'):
					return member.value

			raise ValueError(f"'{v}' is not a valid member of {enum_cls.__name__}")
		return v

	return BeforeValidator(_validate)


class TechnicalEnforcement(AmbyteBaseModel):
	"""
	The canonical technical definition for a regulatory requirement.
	"""

	# --- Common Attributes ---
	action: str | None = Field(default=None, description='The abstract enforcement action.')

	# Apply Validator to RiskSeverity
	risk_level: Annotated[RiskSeverity, validate_enum_by_name(RiskSeverity)] = Field(
		default=RiskSeverity.UNSPECIFIED, description='For AI Act / DPIA classification.'
	)

	tags: list[str] = Field(default_factory=list, description='Tags to apply/check.')

	# --- Geofencing Specifics ---
	strict_residency: bool = False
	allowed_regions: list[str] = Field(default_factory=list)
	denied_regions: list[str] = Field(default_factory=list)

	# --- Purpose Specifics ---
	denied_purposes: list[str] = Field(default_factory=list)
	allowed_purposes: list[str] = Field(default_factory=list)
	required_tag: str | None = None
	requires_explicit_consent: bool = False

	# --- Privacy Specifics ---
	# Apply Validator to PrivacyMethod
	method: Annotated[PrivacyMethod, validate_enum_by_name(PrivacyMethod)] = Field(
		default=PrivacyMethod.UNSPECIFIED,
		description='The privacy enhancing technology required.',
	)
	denied_data_categories: list[str] = Field(default_factory=list)

	# --- Retention Specifics ---
	# Apply Validator to RetentionTrigger
	trigger: Annotated[RetentionTrigger, validate_enum_by_name(RetentionTrigger)] = Field(
		default=RetentionTrigger.UNSPECIFIED
	)
	sla_duration: str | None = Field(None, description="Time duration string (e.g., '30d', '6m').")

	# --- AI Model Specifics ---
	require_human_loop: bool = False
	block_automated_decisions: bool = False
	requires_bias_mitigation: bool = False
	check_parameter: str | None = None
	threshold_value: float | None = None

	# --- Context/Lineage Checks ---
	requires_lineage_check: bool = False
	context_check: dict[str, Any] = Field(default_factory=dict, description='Complex context matching rules.')
	allow_exception_if: str | None = None  # Added field present in yaml

	# --- Documentation ---
	required_documentation: list[str] = Field(default_factory=list)

	# --- Catch-all for extra YAML fields ---
	feature_requirement: str | None = None
	log_retention_period: str | None = None
	operational_constraint: str | None = None
	metadata_requirement: str | None = None
	reporting_requirement: str | None = None
	required_fields: list[str] = Field(default_factory=list)
	phase: str | None = None
	check: str | None = None
	lineage_check: str | None = None
	requires_human_authorization: bool = False
	exception_flow: str | None = None


class RegulatoryClassification(AmbyteBaseModel):
	"""
	High-level categorization of the rule.
	"""

	type: ConstraintType

	# Apply Validator to EnforcementLevel
	severity: Annotated[EnforcementLevel, validate_enum_by_name(EnforcementLevel)] = Field(
		default=EnforcementLevel.AUDIT_ONLY
	)


class MappingRule(AmbyteBaseModel):
	"""
	A single entry in the Knowledge Graph.
	"""

	source_reference: str = Field(..., description="e.g., 'Art. 5(1)(a)'")
	title: str = Field(..., description='Short name of the clause.')
	description: str = Field(..., description='The full legal text or summary used for vector embedding.')
	classification: RegulatoryClassification
	technical_enforcement: TechnicalEnforcement

	@property
	def embedding_text(self) -> str:
		"""
		Constructs the text to be vectorized for semantic search.
		Combines reference, title, and description.
		"""
		return f'{self.source_reference} {self.title}: {self.description}'


class RegulationDefinition(AmbyteBaseModel):
	"""
	The Root Model for a YAML ontology file (e.g., gdpr_mappings.yaml).
	"""

	regulation_id: str = Field(..., description="Unique ID (e.g., 'EU-GDPR-2016/679').")
	title: str = Field(..., description='Full name of the regulation.')
	effective_date: date | str | None = None
	jurisdiction: str = Field(..., description="Geo scope (e.g., 'EU', 'US-CA').")
	mappings: list[MappingRule] = Field(default_factory=list)

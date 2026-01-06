from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field

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


class TechnicalEnforcement(AmbyteBaseModel):
	"""
	The canonical technical definition for a regulatory requirement.
	This serves as the 'Ground Truth' payload in the Regulation Vector Store.

	Instead of asking an LLM to hallucinate parameters, we inject this object
	directly into the policy compiler pipeline.
	"""

	# --- Common Attributes ---
	action: str | None = Field(default=None, description="The abstract enforcement action (e.g., 'block_deployment').")
	risk_level: RiskSeverity = Field(default=RiskSeverity.UNSPECIFIED, description='For AI Act / DPIA classification.')
	tags: list[str] = Field(
		default_factory=list, description="Tags to apply/check (e.g. ['manipulative', 'subliminal'])."
	)

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
	method: str | PrivacyMethod = Field(
		default=PrivacyMethod.UNSPECIFIED,
		description='The privacy enhancing technology required.',
	)
	denied_data_categories: list[str] = Field(default_factory=list)

	# --- Retention Specifics ---
	trigger: str | RetentionTrigger = Field(default=RetentionTrigger.UNSPECIFIED)
	sla_duration: str | None = Field(None, description="Time duration string (e.g., '30d', '6m').")

	# --- AI Model Specifics ---
	require_human_loop: bool = False
	block_automated_decisions: bool = False
	requires_bias_mitigation: bool = False
	check_parameter: str | None = None  # e.g., "training_compute_flops"
	threshold_value: float | None = None  # e.g., 1e25

	# --- Context/Lineage Checks ---
	requires_lineage_check: bool = False
	context_check: dict[str, Any] = Field(
		default_factory=dict, description='Complex context matching rules (e.g. domain=WORKPLACE).'
	)

	# --- Documentation ---
	required_documentation: list[str] = Field(default_factory=list)


class RegulatoryClassification(AmbyteBaseModel):
	"""
	High-level categorization of the rule.
	"""

	type: ConstraintType
	severity: EnforcementLevel = EnforcementLevel.AUDIT_ONLY


class MappingRule(AmbyteBaseModel):
	"""
	A single entry in the Knowledge Graph.
	Maps a specific legal citation to its technical enforcement.
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

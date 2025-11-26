from datetime import timedelta

from ambyte_schemas.models.common import AmbyteBaseModel
from pydantic import Field


class ConflictTrace(AmbyteBaseModel):
	"""
	Audit artifact explaining WHY a specific decision was made.

	In a complex regulatory environment, knowing *that* you blocked a transaction
	is less important than knowing *which* specific clause in *which* contract
	forced that block.
	"""

	winning_obligation_id: str = Field(..., description='The ID of the obligation that dictated the final value.')
	winning_source_id: str = Field(
		..., description="The human-readable source ID (e.g., 'GDPR-Art-17', 'MSA-Clause-9')."
	)
	description: str = Field(
		...,
		description='A natural language explanation of the resolution logic'
		" (e.g., 'Strictest retention period applied').",
	)


class EffectiveRetention(AmbyteBaseModel):
	"""
	The calculated single truth for how long data exists.

	Logic: usually the MINIMUM of all applicable max-retention periods,
	unless a Legal Hold (indefinite) is active.
	"""

	duration: timedelta = Field(..., description='The calculated lifespan of the data.')
	is_indefinite: bool = Field(
		False, description='If True, data cannot be deleted (e.g., Legal Hold). Overrides duration.'
	)
	reason: ConflictTrace


class EffectiveGeofencing(AmbyteBaseModel):
	"""
	The calculated single truth for where data can reside.

	Logic: usually the INTERSECTION of all 'Allowed' lists minus the UNION of all 'Denied' lists.
	"""

	allowed_regions: set[str] = Field(
		default_factory=set, description='The specific ISO codes where data is permitted.'
	)
	blocked_regions: set[str] = Field(
		default_factory=set, description='Regions explicitly forbidden by any active rule.'
	)
	is_global_ban: bool = Field(
		False, description='If True, the intersection resulted in an empty set; data cannot move anywhere.'
	)
	reason: ConflictTrace


class EffectiveAiRules(AmbyteBaseModel):
	"""
	The calculated single truth for AI usage.

	Logic: usually a boolean AND. If one contract forbids training, training is forbidden.
	"""

	training_allowed: bool = Field(False, description='Can this data be used to train new models?')
	fine_tuning_allowed: bool = Field(False, description='Can this data be used to fine-tune existing models?')
	rag_allowed: bool = Field(False, description='Can this data be used in RAG context windows?')

	attribution_required: bool = Field(False, description='Do we need to credit the source?')
	attribution_text: str = Field('', description='Aggregated text required for attribution.')

	reason: ConflictTrace


class ResolvedPolicy(AmbyteBaseModel):
	"""
	The Final Artifact.

	This object represents the 'collapsed' state of all legal obligations applying
	to a specific resource. This is what the Enforcers (Airflow/Snowflake/K8s)
	will actually read and execute.
	"""

	resource_urn: str = Field(..., description='The Unique Resource Name this policy applies to.')

	# The resolved constraints (Optional, because a resource might not have rules in every category)
	retention: EffectiveRetention | None = None
	geofencing: EffectiveGeofencing | None = None
	ai_rules: EffectiveAiRules | None = None

	# Meta-audit
	contributing_obligation_ids: list[str] = Field(
		default_factory=list, description='List of every Obligation ID that was considered during the calculation.'
	)

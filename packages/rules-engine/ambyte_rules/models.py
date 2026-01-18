from datetime import timedelta
from typing import Any

from ambyte_schemas.models.common import AmbyteBaseModel
from ambyte_schemas.models.obligation import PrivacyMethod, RetentionTrigger
from pydantic import Field


class ConflictTrace(AmbyteBaseModel):
	winning_obligation_id: str = Field(..., description='The ID of the obligation that dictated the final value.')
	winning_source_id: str = Field(..., description="The human-readable source ID (e.g., 'GDPR-Art-17').")
	description: str = Field(..., description='A natural language explanation of the resolution logic.')


class EffectiveRetention(AmbyteBaseModel):
	duration: timedelta = Field(..., description='The calculated lifespan of the data.')
	is_indefinite: bool = Field(False, description='If True, data cannot be deleted (e.g., Legal Hold).')
	trigger: RetentionTrigger = Field(..., description='The event that starts the retention clock.')
	reason: ConflictTrace


class EffectiveGeofencing(AmbyteBaseModel):
	allowed_regions: set[str] = Field(default_factory=set)
	blocked_regions: set[str] = Field(default_factory=set)
	is_global_ban: bool = Field(False)
	reason: ConflictTrace


class EffectiveAiRules(AmbyteBaseModel):
	training_allowed: bool = Field(False)
	fine_tuning_allowed: bool = Field(False)
	rag_allowed: bool = Field(False)
	attribution_required: bool = Field(False)
	attribution_text: str = Field('')
	reason: ConflictTrace


class EffectivePurpose(AmbyteBaseModel):
	"""
	The calculated single truth for Purpose Limitation.
	Logic: Intersection of Allowed, Union of Denied.
	"""

	allowed_purposes: set[str] = Field(
		default_factory=set, description='If populated, usage is strictly limited to these purposes.'
	)
	denied_purposes: set[str] = Field(
		default_factory=set, description='Purposes explicitly forbidden by any active rule.'
	)
	reason: ConflictTrace


class EffectivePrivacy(AmbyteBaseModel):
	"""
	The calculated single truth for Privacy Enhancing Technologies (PETs).
	Logic: The "safest" (highest enum value) method wins.
	"""

	method: PrivacyMethod = Field(..., description='The strongest privacy technique required.')
	parameters: dict[str, Any] = Field(default_factory=dict, description='Merged parameters (e.g. epsilon).')
	reason: ConflictTrace


class ResolvedPolicy(AmbyteBaseModel):
	"""
	The Final Artifact.
	"""

	resource_urn: str = Field(..., description='The Unique Resource Name this policy applies to.')

	retention: EffectiveRetention | None = None
	geofencing: EffectiveGeofencing | None = None
	ai_rules: EffectiveAiRules | None = None

	purpose: EffectivePurpose | None = None
	privacy: EffectivePrivacy | None = None

	contributing_obligation_ids: list[str] = Field(
		default_factory=list, description='List of every Obligation ID that was considered.'
	)

from typing import Any

from ambyte_rules.models import ResolvedPolicy
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
	"""
	The standard payload sent by SDKs and Connectors to verify access.
	"""

	resource_urn: str = Field(..., description='The Global Unique Identifier of the asset.')
	action: str = Field(..., description="The operation being attempted (e.g. 'read', 'train').")
	actor_id: str | None = Field(default='anonymous', description='The ID of the user or service.')

	# Context is flexible to allow arbitrary attributes like {'region': 'US', 'purpose': 'BI'}
	context: dict[str, Any] = Field(default_factory=dict)


class CheckResponse(BaseModel):
	"""
	The verdict returned to the client.
	"""

	allowed: bool
	reason: str

	# Diagnostic info
	policy_snapshot: ResolvedPolicy | None = Field(
		default=None, description='The resolved policy used for this decision (if debug mode).'
	)
	cache_hit: bool = False
	trace_id: str | None = None

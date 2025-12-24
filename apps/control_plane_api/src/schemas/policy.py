from ambyte_schemas.models.obligation import EnforcementLevel, Obligation
from pydantic import BaseModel, Field


class ObligationCreate(Obligation):
	"""
	Input payload for creating or updating an Obligation.

	We inherit directly from the canonical `Obligation` schema defined in
	`ambyte-schemas`. This ensures that whatever the CLI/SDK sends
	(generated from YAML) is exactly what the API expects.
	"""

	pass


class BatchObligationCreate(BaseModel):
	"""
	Wrapper for bulk upserts.
	Used by the CLI command `ambyte push` to send multiple policies in one transaction.
	"""

	obligations: list[Obligation] = Field(
		..., description="List of obligations to upsert. Matching is done via the 'id' (slug) field."
	)
	prune: bool = Field(default=False, description='If True, deactivates policies not present in this batch.')


class ObligationFilter(BaseModel):
	"""
	Query parameters for filtering obligations.
	"""

	enforcement_level: EnforcementLevel | None = Field(
		default=None, description='Filter by strictness (e.g., BLOCKING, AUDIT_ONLY)'
	)
	# Allows searching by partial title match
	query: str | None = Field(default=None, description='Search term for title or slug')


class PolicySummary(BaseModel):
	slug: str
	title: str
	status: str  # "CREATED", "UPDATED", "UNCHANGED", "PRUNED"
	version: int


class PushResponse(BaseModel):
	summary: list[PolicySummary]
	dry_run: bool = False

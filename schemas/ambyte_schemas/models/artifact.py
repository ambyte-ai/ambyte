from datetime import datetime, timezone

from ambyte_rules.models import ResolvedPolicy
from pydantic import Field

from ambyte_schemas.models.common import AmbyteBaseModel


class BuildMetadata(AmbyteBaseModel):
	"""
	Context about the compilation environment.
	"""

	compiler_version: str
	generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	# Optional: Git info if provided by the CLI during build
	git_hash: str | None = None
	project_name: str | None = None


class PolicyBundle(AmbyteBaseModel):
	"""
	The Root Artifact written to `local_policies.json`.
	The SDK loads this single object into memory.
	"""

	schema_version: str = Field('1.0', description='Schema version of this artifact.')
	metadata: BuildMetadata

	# The Core Lookup Table: Resource URN -> ResolvedPolicy
	# This enables O(1) lookup during runtime enforcement.
	policies: dict[str, ResolvedPolicy] = Field(default_factory=dict)

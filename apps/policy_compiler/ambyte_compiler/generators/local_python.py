import logging
from importlib import metadata

from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.artifact import BuildMetadata, PolicyBundle

logger = logging.getLogger(__name__)


class LocalPythonGenerator:
	"""
	Generates a localized PolicyBundle artifact.

	This generator serializes the mathematical results of the Rules Engine
	into a highly optimized JSON structure (Hash Map) that the Python SDK
	can load instantly into Pydantic models.
	"""

	def generate(
		self, policies: list[ResolvedPolicy], project_name: str = 'unknown', git_hash: str | None = None
	) -> str:
		"""
		Creates the 'local_policies.json' content.

		Args:
		    policies: A list of ResolvedPolicy objects (the output of the Rules Engine).
		    project_name: The name of the workspace project.
		    git_hash: Optional git revision for audit provenance.

		Returns:
		    A JSON string representing the complete PolicyBundle.
		"""  # noqa: E101
		# 1. Determine Compiler Version
		try:
			compiler_version = metadata.version('ambyte-compiler')
		except metadata.PackageNotFoundError:
			compiler_version = 'dev'

		# 2. Build Metadata
		meta = BuildMetadata(compiler_version=compiler_version, project_name=project_name, git_hash=git_hash)

		# 3. Transform List -> Hash Map (O(1) Lookup)
		# We index by resource_urn to allow the SDK to do `policies.get("urn:...")`
		policy_map = {p.resource_urn: p for p in policies}

		# 4. Construct the Bundle
		bundle = PolicyBundle(metadata=meta, policies=policy_map, schema_version='1.0')

		logger.info('Generated Local Bundle with %s policies.', len(policy_map))

		# 5. Serialize to JSON
		# exclude_none=True significantly reduces bundle size by removing unset constraints
		return bundle.model_dump_json(indent=2, exclude_none=True)

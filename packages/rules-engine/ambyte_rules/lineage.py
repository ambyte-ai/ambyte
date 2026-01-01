from ambyte_schemas.models.common import RiskSeverity, SensitivityLevel

from ambyte_rules.interfaces import MetadataProvider


class LineageGraph:
	"""
	Stateless logic layer for analyzing the dependency graph.

	Unlike previous versions, this does NOT store the graph in memory.
	It delegates traversal and metadata retrieval to an injected `MetadataProvider`.
	"""

	def __init__(self, provider: MetadataProvider):
		"""
		Args:
		    provider: An implementation (e.g., Postgres, Neo4j, or Mock) that
		              handles the physical retrieval of nodes and edges.
		"""  # noqa: E101
		self.provider = provider

	async def get_inherited_risk(self, target_urn: str) -> RiskSeverity:
		"""
		Walks upstream to find the MAXIMUM risk level of any ancestor.

		Logic: A model trained on High Risk data is High Risk.
		"""
		# 1. Get all ancestors via the provider (e.g., Recursive SQL CTE)
		ancestors = await self.provider.get_upstream_ancestors(target_urn)

		# 2. Include the node itself (in case it has intrinsic risk explicitly set)
		nodes_to_check = set(ancestors)
		nodes_to_check.add(target_urn)

		max_risk = RiskSeverity.UNSPECIFIED

		# 3. Iterate and compute max
		# Note: In a highly optimized setup, the provider might offer a
		# 'get_max_risk_upstream(urn)' method to do this entirely in SQL.
		for node_urn in nodes_to_check:
			meta = await self.provider.get_node_metadata(node_urn)
			risk = meta.get('risk', RiskSeverity.UNSPECIFIED)

			# Assuming enum values are ordered integers (0=Unspecified, 4=Unacceptable)
			if risk > max_risk:
				max_risk = risk

		return max_risk

	async def get_inherited_sensitivity(self, target_urn: str) -> SensitivityLevel:
		"""
		Walks upstream to find the MAXIMUM sensitivity.

		Logic: Mixing Public data with Confidential data results in Confidential data.
		"""
		ancestors = await self.provider.get_upstream_ancestors(target_urn)

		nodes_to_check = set(ancestors)
		nodes_to_check.add(target_urn)

		max_sens = SensitivityLevel.UNSPECIFIED

		for node_urn in nodes_to_check:
			meta = await self.provider.get_node_metadata(node_urn)
			sens = meta.get('sensitivity', SensitivityLevel.UNSPECIFIED)

			if sens > max_sens:
				max_sens = sens

		return max_sens

	async def get_poisoned_constraints(self, target_urn: str) -> list[str]:
		"""
		Identifies upstream nodes that explicitly FORBID downstream usage.

		Example: If Dataset A has 'ai_training_allowed=False', and Target B
		is a descendant, return A's URN as a blocker.
		"""
		ancestors = await self.provider.get_upstream_ancestors(target_urn)

		poison_sources = []
		for node_urn in ancestors:
			meta = await self.provider.get_node_metadata(node_urn)

			# Check explicit flag. Default to True (Allowed) if not set.
			# Only if explicitly False do we flag it.
			if meta.get('ai_training_allowed') is False:
				poison_sources.append(node_urn)

		return poison_sources

import logging
from typing import Any

from ambyte_rules.interfaces import MetadataProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.inventory import Resource
from src.db.models.lineage import LineageEdge

logger = logging.getLogger(__name__)


class PostgresMetadataProvider(MetadataProvider):
	"""
	Production implementation of the MetadataProvider interface.

	Features:
	1. Uses Recursive Common Table Expressions (CTEs) for efficient graph traversal in Postgres.
	2. Maps the loose JSONB 'attributes' column in the DB to the structured
	   schema expected by the Rules Engine.
	"""  # noqa: E101

	def __init__(self, db: AsyncSession):
		self.db = db

	async def get_upstream_ancestors(self, urn: str) -> list[str]:
		"""
		Performs a recursive upstream traversal using SQL.
		Finds all URNs that eventually flow INTO the target URN.
		"""
		# 1. Define the Recursive CTE
		ancestors_cte = select(LineageEdge.source_urn).where(LineageEdge.target_urn == urn).cte(recursive=True)

		# Recursive Step: Parents of the parents
		# JOIN lineage_edges ON lineage_edges.target_urn = ancestors_cte.source_urn
		ancestors_alias = ancestors_cte.alias()
		edges_alias = LineageEdge.__table__.alias()

		recursive_part = select(edges_alias.c.source_urn).join(
			ancestors_alias, edges_alias.c.target_urn == ancestors_alias.c.source_urn
		)

		# Combine Base + Recursive
		ancestors_cte = ancestors_cte.union_all(recursive_part)

		# 2. Execute the Final Query
		stmt = select(ancestors_cte)
		result = await self.db.execute(stmt)

		# 3. Flatten results
		return list(result.scalars().all())

	async def get_node_metadata(self, urn: str) -> dict[str, Any]:
		"""
		Fetches resource attributes from the 'resources' table.
		"""
		# 1. Fetch Resource by URN
		stmt = select(Resource).where(Resource.urn == urn).limit(1)
		result = await self.db.execute(stmt)
		resource = result.scalars().first()

		if not resource:
			return {}

		# 2. Extract JSONB Attributes
		attrs = resource.attributes or {}

		# We construct the normalized metadata dictionary
		metadata = {
			# Standard Enums (stored as ints or strings in JSON)
			'risk': attrs.get('risk_level', 0),  # Default UNSPECIFIED
			'sensitivity': attrs.get('sensitivity', 0),  # Default UNSPECIFIED
			# Tags dictionary
			'tags': attrs.get('tags', {}),
			# Specific Constraints
			# Look for explicit overrides in the attributes
			'ai_training_allowed': attrs.get('ai_training_allowed', True),
		}

		return metadata

from abc import ABC, abstractmethod
from typing import Any


class MetadataProvider(ABC):
	"""
	Interface for retrieving node attributes and graph structure.

	This decouples the Rules Engine from the persistence layer, allowing
	implementations to swap between in-memory dictionaries (for testing/local)
	and database storage (Postgres/GraphDB) for production.
	"""

	@abstractmethod
	async def get_node_metadata(self, urn: str) -> dict[str, Any]:
		"""
		Retrieves the attributes associated with a specific resource URN.

		Args:
		    urn: The Unique Resource Name to lookup.

		Returns:
		    A dictionary of metadata attributes.
		    Expected keys include:
		    - 'risk' (int/enum value)
		    - 'sensitivity' (int/enum value)
		    - 'ai_training_allowed' (bool)
		    - 'tags' (dict)

		    Returns an empty dict if the node is not found.
		"""  # noqa: E101
		pass

	@abstractmethod
	async def get_upstream_ancestors(self, urn: str) -> list[str]:
		"""
		Retrieves the list of all upstream dependencies (ancestors) for a given URN.

		This method is responsible for performing the graph traversal
		(e.g., via Recursive CTE in SQL or NetworkX traversal in memory).

		Args:
		    urn: The target resource URN.

		Returns:
		    A list of URN strings representing all nodes that feed data INTO the target.
		"""  # noqa: E101
		pass

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ambyte_schemas.models.obligation import Obligation

# The Generic Type Variable.
# Represents the specific "Effective" model returned by a solver (e.g., EffectiveRetention).
T = TypeVar('T')


class BaseSolver(ABC, Generic[T]):
	"""
	Abstract Base Class for all Conflict Resolution strategies.

	Each domain (Time, Geography, Usage) requires different mathematical logic
	to resolve conflicts. This class enforces a standard interface for taking
	a raw list of Obligations and reducing them to a single 'Effective' truth.
	"""

	@abstractmethod
	def resolve(self, obligations: list[Obligation]) -> T | None:
		"""
		The core logic function.

		        Args:
		              obligations: A list of all raw Obligation objects that apply to a resource.
		            The solver is responsible for filtering this list for
		            relevant constraints (e.g., ignoring Geo rules if this is
		            a Retention solver).

		          Returns:
		    The resolved 'Effective' policy object of type T, or None if no
		    relevant obligations were found in the input list.
		"""  # noqa: E101
		pass

from ambyte_schemas.models.obligation import Obligation

from ambyte_rules.models import ResolvedPolicy
from ambyte_rules.solvers.ai import AiSolver
from ambyte_rules.solvers.geo import GeofencingSolver
from ambyte_rules.solvers.privacy import PrivacySolver
from ambyte_rules.solvers.purpose import PurposeSolver
from ambyte_rules.solvers.retention import RetentionSolver


class ConflictResolutionEngine:
	"""
	The Central Brain of the Ambyte Policy Platform.

	This engine accepts a list of abstract, potentially conflicting legal Obligations
	and reduces them to a single, mathematically rigorous 'Effective Policy'.
	"""

	def __init__(self):
		# Initialize specific strategy solvers
		self.retention_solver = RetentionSolver()
		self.geo_solver = GeofencingSolver()
		self.ai_solver = AiSolver()
		self.purpose_solver = PurposeSolver()
		self.privacy_solver = PrivacySolver()

	def resolve(self, resource_urn: str, obligations: list[Obligation]) -> ResolvedPolicy:
		"""
		Calculates the Effective Policy for a specific resource.

		Args:
			resource_urn: The Unique Resource Name (e.g. "urn:snowflake:sales")
			obligations: A list of ALL raw obligations that apply to this resource.

		Returns:
			A ResolvedPolicy object containing the computed Truth for all domains.
		"""

		# 1. Solve for Time (Retention)
		effective_retention = self.retention_solver.resolve(obligations)

		# 2. Solve for Space (Geofencing)
		effective_geo = self.geo_solver.resolve(obligations)

		# 3. Solve for Usage (AI/ML)
		effective_ai = self.ai_solver.resolve(obligations)

		# 4. Solve for Intent (Purpose)
		effective_purpose = self.purpose_solver.resolve(obligations)

		# 5. Solve for Security (Privacy Methods)
		effective_privacy = self.privacy_solver.resolve(obligations)

		# 6. Assemble the Final Artifact
		return ResolvedPolicy(
			resource_urn=resource_urn,
			retention=effective_retention,
			geofencing=effective_geo,
			ai_rules=effective_ai,
			purpose=effective_purpose,
			privacy=effective_privacy,
			# Metadata: Record which inputs were processed
			contributing_obligation_ids=[o.id for o in obligations],
		)

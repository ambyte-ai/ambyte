from datetime import timedelta

from ambyte_rules.models import ConflictTrace, EffectiveRetention
from ambyte_rules.solvers.base import BaseSolver
from ambyte_schemas.models.obligation import Obligation, RetentionRule


class RetentionSolver(BaseSolver[EffectiveRetention]):
	"""
	Resolves conflicts between multiple Data Retention policies.

	Strategy: Data Minimization (Shortest TTL Wins).
	If multiple obligations define a maximum retention period, the strictest
	(shortest) period is selected as the Effective Retention.

	Example:
	- Contract A: Retain for max 5 years.
	- GDPR Policy: Retain for max 2 years.
	- Result: 2 years (Satisfies GDPR, and is within the 5-year limit of Contract A).
	"""

	def resolve(self, obligations: list[Obligation]) -> EffectiveRetention | None:
		# 1. Filter for relevant obligations
		relevant_obs = [o for o in obligations if o.retention is not None]

		if not relevant_obs:
			return None

		# 2. Initialize variables for finding the minimum duration
		# Start with the maximum possible time to ensure the first rule overwrites it.
		min_duration = timedelta.max
		winning_ob: Obligation | None = None
		winning_rule: RetentionRule | None = None

		# 3. Iterate and Solve
		for ob in relevant_obs:
			rule: RetentionRule = ob.retention  # type: ignore

			# The Core Logic: Find the shortest duration
			if rule.duration < min_duration:
				min_duration = rule.duration
				winning_ob = ob
				winning_rule = rule

		# Safety check (should technically be unreachable due to relevant_obs check)
		if winning_ob is None or winning_rule is None:
			return None

		# 4. Construct the Result
		return EffectiveRetention(
			duration=min_duration,
			# In this context, 'is_indefinite' would be True if we had an explicit "Keep Forever" rule.
			# For now, we default to False unless specific logic dictates otherwise.
			# The legal hold *capability* is noted, but doesn't automatically make retention indefinite
			# unless a hold is actually active (which would be a runtime check, not a static rule check).
			trigger=winning_rule.trigger,
			is_indefinite=False,
			reason=ConflictTrace(
				winning_obligation_id=winning_ob.id,
				winning_source_id=winning_ob.provenance.source_id,
				description=(
					f"Applied strictest retention limit from '{winning_ob.title}'. "
					f'Calculated shortest duration among {len(relevant_obs)} competing rules.'
				),
			),
		)

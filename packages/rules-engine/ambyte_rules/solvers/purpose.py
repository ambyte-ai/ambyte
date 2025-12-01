from ambyte_rules.models import ConflictTrace, EffectivePurpose
from ambyte_rules.solvers.base import BaseSolver
from ambyte_schemas.models.obligation import Obligation, PurposeRestriction


class PurposeSolver(BaseSolver[EffectivePurpose]):
	"""
	Resolves conflicts between multiple Purpose Limitation policies.

	Strategy:
	1. Allowed Purposes: INTERSECTION (Data can only be used for purposes common to ALL allow-lists).
	2. Denied Purposes: UNION (If any rule blocks a purpose, it is blocked).
	"""

	def resolve(self, obligations: list[Obligation]) -> EffectivePurpose | None:
		relevant_obs = [o for o in obligations if o.purpose is not None]
		if not relevant_obs:
			return None

		# 1. Initialize
		# None implies "Everything is allowed" until restricted
		effective_allowed: set[str] | None = None
		global_denied: set[str] = set()

		winning_ob = relevant_obs[0]

		# 2. Iterate
		for ob in relevant_obs:
			rule: PurposeRestriction = ob.purpose  # type: ignore

			# A. Union of Denials
			if rule.denied_purposes:
				global_denied.update(rule.denied_purposes)
				# If this rule adds denials, it contributes to the strictness
				if not effective_allowed:
					winning_ob = ob

			# B. Intersection of Allowances
			if rule.allowed_purposes:
				current_set = set(rule.allowed_purposes)

				if effective_allowed is None:
					# First restrictor found
					effective_allowed = current_set
					winning_ob = ob
				else:
					# Intersect with existing constraints
					prev_len = len(effective_allowed)
					effective_allowed = effective_allowed.intersection(current_set)

					if len(effective_allowed) < prev_len:
						winning_ob = ob

		# 3. Finalize
		# If effective_allowed is still None, it means no rule restricted the positive scope.
		final_allowed = effective_allowed if effective_allowed is not None else set()

		# If we have both lists, we should technically remove denied from allowed
		# to be cleaner, though the enforcement engine usually checks both.
		if final_allowed:
			final_allowed = final_allowed - global_denied

		return EffectivePurpose(
			allowed_purposes=final_allowed,
			denied_purposes=global_denied,
			reason=ConflictTrace(
				winning_obligation_id=winning_ob.id,
				winning_source_id=winning_ob.provenance.source_id,
				description=(
					f"Applied purpose intersection from '{winning_ob.provenance.source_id}'. "
					f'Result: {len(final_allowed)} allowed, {len(global_denied)} denied.'
				),
			),
		)

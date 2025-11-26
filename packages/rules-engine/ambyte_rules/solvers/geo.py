from ambyte_rules.models import ConflictTrace, EffectiveGeofencing
from ambyte_rules.solvers.base import BaseSolver
from ambyte_schemas.models.obligation import GeofencingRule, Obligation


class GeofencingSolver(BaseSolver[EffectiveGeofencing]):
	"""
	Resolves conflicts between multiple Data Residency/Geofencing policies.

	Strategy: Intersection of Permissions, Union of Prohibitions.
	1. Data is only allowed in regions that appear in ALL 'Allowed' lists.
	2. Data is strictly forbidden in regions that appear in ANY 'Denied' list.
	"""

	def resolve(self, obligations: list[Obligation]) -> EffectiveGeofencing | None:
		# 1. Filter for relevant obligations
		relevant_obs = [o for o in obligations if o.geofencing is not None]

		if not relevant_obs:
			return None

		# 2. Initialize Sets
		# We start 'effective_allowed' as None to distinguish between
		# "No allowed list provided (Global Allowed)" vs "Empty allowed list (Global Ban)".
		effective_allowed: set[str] | None = None
		global_denied: set[str] = set()

		# Track the primary constraint driver for the audit trail
		winning_ob = relevant_obs[0]

		# 3. Iterate and Solve
		for ob in relevant_obs:
			rule: GeofencingRule = ob.geofencing  # type: ignore

			# A. Aggregating Denials (Union)
			# If ANY rule says "No", it is "No".
			global_denied.update(rule.denied_regions)

			# B. Intersecting Allowances
			# If a rule specifies allowed regions, the world shrinks to that subset.
			if rule.allowed_regions:
				current_set = set(rule.allowed_regions)

				if effective_allowed is None:
					# This is the first rule restricting scope.
					effective_allowed = current_set
					winning_ob = ob
				else:
					# Intersection: The resulting set must be in BOTH previous allowed AND current allowed.
					previous_len = len(effective_allowed)
					effective_allowed = effective_allowed.intersection(current_set)

					# If this rule shrank the world, credit it as the "Winner"
					if len(effective_allowed) < previous_len:
						winning_ob = ob

			# C. Strict Residency Flag
			# If a rule has strict_residency=True, it usually implies the allowed_regions
			# are the ONLY places allowed. This reinforces the intersection logic above.
			# We don't need special handling here because intersection handles the logic,
			# but we could use it for metadata if needed.

		# 4. Final Calculation
		is_global_ban = False

		if effective_allowed is None:
			# Case: No rule specified an 'allowed' list.
			# This implies "Allowed Everywhere except Denied list".
			# For the output object, we leave allowed_regions empty to signify "Universe",
			# but we return the explicitly denied list.
			final_allowed = set()
		else:
			# Case: We have an explicit allowed list.
			# We must subtract any explicitly denied regions from it.
			final_allowed = effective_allowed - global_denied

			# If the intersection resulted in zero regions, the data has nowhere to go.
			if len(final_allowed) == 0:
				is_global_ban = True

		# 5. Construct Result
		description = (
			f'Calculated intersection of {len(relevant_obs)} geofencing rules. '
			f'{len(global_denied)} regions explicitly denied.'
		)

		if is_global_ban:
			description += ' RESULT: GLOBAL BAN (Intersection is empty).'

		return EffectiveGeofencing(
			allowed_regions=final_allowed,
			blocked_regions=global_denied,
			is_global_ban=is_global_ban,
			reason=ConflictTrace(
				winning_obligation_id=winning_ob.id,
				winning_source_id=winning_ob.provenance.source_id,
				description=description,
			),
		)

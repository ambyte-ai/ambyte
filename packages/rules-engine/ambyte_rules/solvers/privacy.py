import logging
from typing import Any

from ambyte_rules.models import ConflictTrace, EffectivePrivacy
from ambyte_rules.solvers.base import BaseSolver
from ambyte_schemas.models.obligation import Obligation, PrivacyEnhancementRule, PrivacyMethod

logger = logging.getLogger(__name__)


class PrivacySolver(BaseSolver[EffectivePrivacy]):
	"""
	Resolves conflicts between multiple Privacy Enhancement techniques.

	Strategy:
	1. Method Hierarchy: Higher enum values imply stricter categories (e.g., Anonymization > Pseudonymization).
	2. Parameter Merging:
	- Differential Privacy: Minimal Epsilon (Strictest Budget).
	- K-Anonymity: Maximal K (Largest Group).
	- Configuration: Strict Equality.
	"""

	def resolve(self, obligations: list[Obligation]) -> EffectivePrivacy | None:
		relevant_obs = [o for o in obligations if o.privacy is not None]
		if not relevant_obs:
			return None

		# 1. Initialize with the first rule
		first_ob = relevant_obs[0]
		current_rule: PrivacyEnhancementRule = first_ob.privacy  # type: ignore

		best_method = PrivacyMethod(current_rule.method)
		merged_params = current_rule.parameters.copy()
		winning_ob = first_ob

		# 2. Iterate remaining rules
		for ob in relevant_obs[1:]:
			new_rule: PrivacyEnhancementRule = ob.privacy  # type: ignore

			new_method = PrivacyMethod(new_rule.method)
			# Case A: New method is strictly stronger (Hierarchy check)
			# Assumption: Enum values are ordered by strictness (0=Unspecified ... 3=DiffPrivacy)
			if new_method.value > best_method.value:
				best_method = new_method
				merged_params = new_rule.parameters.copy()
				winning_ob = ob
				continue

			# Case B: New method is strictly weaker
			if new_method.value < best_method.value:
				# The current best_method satisfies the weaker rule's category requirement,
				# so we stick with the current winner.
				continue

			# Case C: Same Method - Merge Parameters smartly
			if new_method == best_method.value:
				try:
					merged_params = self._merge_parameters(best_method, merged_params, new_rule.parameters)
				# If merging resulted in tighter constraints that originated from the new rule,
				# we could technically swap the winning_ob, but "Hybrid" is the real winner.
				# We keep the original winner for provenance or update if the new rule drove the specific value.
				except ValueError as e:
					logger.error('Unresolvable privacy conflict for resource %s: %s', ob.id, e)
					raise ValueError(f'Conflicting privacy parameters between obligations: {e}') from e

		return EffectivePrivacy(
			method=best_method,
			parameters=merged_params,
			reason=ConflictTrace(
				winning_obligation_id=winning_ob.id,
				winning_source_id=winning_ob.provenance.source_id,
				description=(
					f"Enforced strongest privacy method '{best_method.name}' with parameters: {merged_params}."
				),
			),
		)

	def _merge_parameters(self, method: PrivacyMethod, current: dict[str, str], new: dict[str, str]) -> dict[str, Any]:
		"""
		Mathematically composes parameters based on the privacy definition.
		"""
		merged = current.copy()

		if method == PrivacyMethod.DIFFERENTIAL_PRIVACY:
			# Logic: MIN Epsilon (Lower is more private), MIN Delta

			# Epsilon
			curr_eps = float(current.get('epsilon', '10.0'))  # Default loose
			new_eps = float(new.get('epsilon', '10.0'))
			merged['epsilon'] = str(min(curr_eps, new_eps))

			# Delta
			if 'delta' in current or 'delta' in new:
				curr_delta = float(current.get('delta', '1.0'))
				new_delta = float(new.get('delta', '1.0'))
				merged['delta'] = str(min(curr_delta, new_delta))

			return merged

		if method == PrivacyMethod.ANONYMIZATION:
			# Logic: MAX K (Higher k-anonymity is more private), MAX L (l-diversity)

			# K-Anonymity
			if 'k' in current or 'k' in new:
				curr_k = int(current.get('k', '0'))
				new_k = int(new.get('k', '0'))
				merged['k'] = str(max(curr_k, new_k))

			# L-Diversity
			if 'l' in current or 'l' in new:
				curr_l = int(current.get('l', '0'))
				new_l = int(new.get('l', '0'))
				merged['l'] = str(max(curr_l, new_l))

			return merged

		# Logic: Strict Equality for Configuration Strings (Pseudonymization, Encryption Algos)
		# If one rule says "SHA256" and another says "AES256", we cannot merge.
		for key, val in new.items():
			if key in current:
				if current[key] != val:
					# Specific exception for algorithm mismatch
					raise ValueError(
						f"Conflicting configuration for {key}: '{current[key]}' vs '{val}'. "
						'Cannot satisfy both simultaneously.'
					)
			else:
				merged[key] = val

		return merged

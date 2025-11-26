from ambyte_rules.models import ConflictTrace, EffectiveAiRules
from ambyte_rules.solvers.base import BaseSolver
from ambyte_schemas.models.obligation import AiModelConstraint, Obligation


class AiSolver(BaseSolver[EffectiveAiRules]):
	"""
	Resolves conflicts between multiple AI Model usage constraints.

	Strategy: Precautionary Principle (Restrictive AND).
	- If ANY rule forbids Training, Training is Forbidden.
	- If ANY rule forbids Fine-Tuning, Fine-Tuning is Forbidden.
	- If ANY rule requires Attribution, Attribution is Required.

	This ensures that a single rigorous contract (e.g., "Do not use for GenAI")
	is not overridden by a looser general policy.
	"""

	def resolve(self, obligations: list[Obligation]) -> EffectiveAiRules | None:
		# 1. Filter for relevant obligations
		relevant_obs = [o for o in obligations if o.ai_model is not None]

		if not relevant_obs:
			return None

		# 2. Initialize defaults (Permissive start)
		# We assume allowed unless restricted, because the presence of an Obligation
		# object implies we are checking specific constraints.
		can_train = True
		can_finetune = True
		can_rag = True

		attribution_needed = False
		attribution_texts: list[str] = []

		# Track the obligation responsible for the most significant restriction (Training Ban)
		# Default to the first one in case no restrictions are found.
		winning_ob = relevant_obs[0]

		# 3. Iterate and Solve (Boolean Logic)
		for ob in relevant_obs:
			rule: AiModelConstraint = ob.ai_model  # type: ignore

			# A. Training (The big switch)
			if not rule.training_allowed:
				if can_train:
					# This is the first rule to flip the switch to False.
					# It is the "reason" we are blocking.
					can_train = False
					winning_ob = ob

			# B. Fine-Tuning
			if not rule.fine_tuning_allowed:
				can_finetune = False

			# C. RAG / Context Window
			if not rule.rag_usage_allowed:
				can_rag = False

			# D. Attribution (Additive)
			# If any rule demands attribution, we must provide it.
			if rule.attribution_text_required:
				attribution_needed = True
				attribution_texts.append(rule.attribution_text_required)

				# If we are strictly attributing but allowing training, this might be the 'winner'
				# relative to the attribution decision.
				if can_train and winning_ob == relevant_obs[0]:
					winning_ob = ob

		# 4. Construct Result

		# Build a dynamic description string
		desc_parts = []
		if not can_train:
			desc_parts.append('Training Blocked')
		if not can_finetune:
			desc_parts.append('Fine-Tuning Blocked')
		if attribution_needed:
			desc_parts.append('Attribution Required')

		desc_str = ', '.join(desc_parts) if desc_parts else 'All AI actions permitted'

		return EffectiveAiRules(
			training_allowed=can_train,
			fine_tuning_allowed=can_finetune,
			rag_allowed=can_rag,
			attribution_required=attribution_needed,
			attribution_text='; '.join(attribution_texts),
			reason=ConflictTrace(
				winning_obligation_id=winning_ob.id,
				winning_source_id=winning_ob.provenance.source_id,
				description=f"AI Constraint: {desc_str}. Defined by source '{winning_ob.provenance.source_id}'.",
			),
		)

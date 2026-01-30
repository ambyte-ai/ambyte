import logging
from datetime import datetime, timezone
from typing import Any

from ambyte_rules.models import (
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePrivacy,
	EffectivePurpose,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import PrivacyMethod

logger = logging.getLogger('ambyte.core.evaluator')


class LocalPolicyEvaluator:
	"""
	Pure Python implementation of the Ambyte Policy Logic.

	This class takes a compiled 'ResolvedPolicy' (the Contract) and
	compares it against the runtime 'context' (the Reality).
	It returns a boolean decision (ALLOW/DENY).
	"""

	def evaluate(self, policy: ResolvedPolicy, action: str, context: dict[str, Any]) -> tuple[bool, str]:
		"""
		Main entry point for evaluation.

		Returns:
		    (is_allowed: bool, reason: str)
		"""  # noqa: E101
		# 1. Check Geofencing (Space)
		if policy.geofencing:
			allowed, reason = self._check_geo(policy.geofencing, context)
			if not allowed:
				return False, reason

		# 2. Check Purpose Limitation (Intent)
		if policy.purpose:
			allowed, reason = self._check_purpose(policy.purpose, context)
			if not allowed:
				return False, reason

		# 3. Check AI/ML Rules (Usage)
		if policy.ai_rules:
			allowed, reason = self._check_ai(policy.ai_rules, action)
			if not allowed:
				return False, reason

		# 4. Check Retention (Time)
		if policy.retention:
			allowed, reason = self._check_retention(policy.retention, context)
			if not allowed:
				return False, reason

		# 5. Check Privacy (Transformation)
		if policy.privacy:
			allowed, reason = self._check_privacy(policy.privacy, context)
			if not allowed:
				return False, reason

		return True, 'Access Allowed'

	def _check_geo(self, rule: EffectiveGeofencing, context: dict) -> tuple[bool, str]:
		"""
		Validates data residency requirements.
		"""
		if rule.is_global_ban:
			return False, f'Global Data Ban active (Source: {rule.reason.winning_source_id})'

		# Extract region from context (case-insensitive keys)
		current_region = self._get_context_val(context, ['region', 'geo', 'location', 'country'])

		if not current_region:
			# Fail closed if location is required but unknown
			# If no allowed/blocked lists exist, it's open, but if lists exist, we need to know.
			if rule.allowed_regions or rule.blocked_regions:
				return False, "Context missing 'region' attribute required for geofencing."
			return True, 'No specific geo restrictions.'

		current_region = str(current_region).upper()

		# 1. Check Blocklist
		if current_region in rule.blocked_regions:
			return False, f"Region '{current_region}' is explicitly blocked."

		# 2. Check Allowlist (if present)
		if rule.allowed_regions and current_region not in rule.allowed_regions:
			return False, f"Region '{current_region}' is not in the allowed list."

		return True, 'Region allowed'

	def _check_purpose(self, rule: EffectivePurpose, context: dict) -> tuple[bool, str]:
		"""
		Validates purpose limitation.
		"""
		current_purpose = self._get_context_val(context, ['purpose', 'intent', 'usage'])

		if not current_purpose:
			# If purpose is restricted, we can't allow "unknown" usage.
			if rule.allowed_purposes or rule.denied_purposes:
				return False, "Context missing 'purpose' attribute."
			return True, 'No purpose restrictions.'

		current_purpose = str(current_purpose).upper()

		# 1. Check Denied
		if current_purpose in rule.denied_purposes:
			return False, f"Purpose '{current_purpose}' is forbidden."

		# 2. Check Allowed
		if rule.allowed_purposes and current_purpose not in rule.allowed_purposes:
			return False, f"Purpose '{current_purpose}' is not explicitly allowed."

		return True, 'Purpose allowed'

	def _check_ai(self, rule: EffectiveAiRules, action: str) -> tuple[bool, str]:
		"""
		Validates AI-specific actions like training or RAG.
		"""
		act = action.lower()

		# Heuristic mapping of verbs to constraints

		if 'train' in act:
			if not rule.training_allowed:
				return False, 'AI Training is prohibited by policy.'

		if 'fine' in act and 'tune' in act:  # fine_tune, finetune
			if not rule.fine_tuning_allowed:
				return False, 'Model Fine-Tuning is prohibited by policy.'

		if 'rag' in act or 'retrieval' in act:
			if not rule.rag_allowed:
				return False, 'RAG/Retrieval usage is prohibited by policy.'

		return True, 'AI action allowed'

	def _check_retention(self, rule: EffectiveRetention, context: dict) -> tuple[bool, str]:
		"""
		Validates data expiration.
		"""
		if rule.is_indefinite:
			return True, 'Data under Legal Hold (Indefinite Retention).'

		# We need a reference date (when the data was created)
		creation_date_val = self._get_context_val(context, ['created_at', 'creation_date', 'date'])

		if not creation_date_val:
			# If we don't know how old it is, strictly speaking we can't enforce retention.
			# We log a warning but usually fail-open or fail-closed depending on risk appetite.
			# Ambyte default: Warn and Allow (to avoid breaking pipelines due to bad metadata).
			logger.debug("Retention rule exists but 'created_at' missing in context. Skipping check.")
			return True, 'Skipped (Missing Metadata)'

		try:
			# Parse Creation Date
			if isinstance(creation_date_val, str):
				created_at = datetime.fromisoformat(creation_date_val)
			elif isinstance(creation_date_val, datetime):
				created_at = creation_date_val
			else:
				return True, 'Skipped (Invalid Date Format)'

			# Ensure UTC for math
			if created_at.tzinfo is None:
				created_at = created_at.replace(tzinfo=timezone.utc)

			now = datetime.now(timezone.utc)
			age = now - created_at

			if age > rule.duration:
				return False, f'Data expired. Age {age.days}d > Limit {rule.duration.days}d.'

		except Exception as e:
			logger.warning('Error checking retention: %s', e)
			return True, 'Skipped (Error)'

		return True, 'Retention valid'

	def _check_privacy(self, rule: EffectivePrivacy, context: dict) -> tuple[bool, str]:
		"""
		Validates privacy transformation requirements (Masking/Anonymization).

		Logic:
		1. If the policy requires privacy (Method != UNSPECIFIED)...
		2. AND the user explicitly requests 'raw' or 'unmasked' output format...
		3. THEN Block access.

		Otherwise, ALLOW (assuming the downstream system handles the masking).
		"""
		if rule.method == PrivacyMethod.UNSPECIFIED:
			return True, 'No specific privacy method required.'

		requested_format = self._get_context_val(context, ['output_format', 'mode', 'format'])

		if requested_format:
			fmt = str(requested_format).lower().strip()
			# Block explicit requests for cleartext on protected resources
			if fmt in ['raw', 'cleartext', 'unmasked', 'decrypt']:
				method_name = rule.method.name if hasattr(rule.method, 'name') else str(rule.method)
				return False, f"Access Denied: Policy requires '{method_name}', but '{fmt}' output was requested."

		return True, 'Allowed (Transformation delegated to downstream).'

	def _get_context_val(self, context: dict, keys: list[str]) -> Any | None:
		"""Helper to find a value using multiple potential key names (case-insensitive)."""
		# Normalize context keys for search
		context_lower = {k.lower(): v for k, v in context.items()}

		for key in keys:
			if key in context:
				return context[key]
			if key.lower() in context_lower:
				return context_lower[key.lower()]
		return None

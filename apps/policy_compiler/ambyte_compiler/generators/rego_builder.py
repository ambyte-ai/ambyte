from datetime import datetime
from typing import Any

from ambyte_rules.models import ResolvedPolicy


class RegoDataBuilder:
	"""
	Transforms the resolved Ambyte Policy into the JSON Data Bundle
	structure expected by Open Policy Agent (OPA).

	Instead of generating Rego code dynamically, we generate the *data*
	that the static Rego policies evaluate against.

	Output Structure Example:
	{
	    "resource_urn": "urn:snowflake:sales",
	    "retention": { ... },
	    "geofencing": { ... },
	    "ai_rules": { ... },
	    "purpose": {
	        "allowed_purposes": ["ANALYTICS"],
	        "denied_purposes": ["MARKETING"]
	    },
	    "privacy": {
	        "method": "DIFFERENTIAL_PRIVACY",
	        "parameters": {"epsilon": "0.5"}
	    }
	}
	"""  # noqa: E101

	def build_bundle_data(self, policy: ResolvedPolicy) -> dict[str, Any]:
		"""
		Args:
			policy: The mathematical result from the ConflictResolutionEngine.

		Returns:
			A dictionary ready to be serialized to 'data.json' for OPA.
		"""
		bundle = {
			'resource_urn': policy.resource_urn,
			'meta': {
				'contributing_obligations': policy.contributing_obligation_ids,
				'generated_at_iso': datetime.now().isoformat(),
			},
		}

		# 1. Retention Data
		if policy.retention:
			bundle['retention'] = {
				'max_seconds': int(policy.retention.duration.total_seconds()),
				'is_indefinite': policy.retention.is_indefinite,
				'reason_code': policy.retention.reason.winning_source_id,
			}

		# 2. Geofencing Data
		if policy.geofencing:
			bundle['geofencing'] = {
				# Convert sets to sorted lists for deterministic JSON
				'allowed_regions': sorted(policy.geofencing.allowed_regions),
				'blocked_regions': sorted(policy.geofencing.blocked_regions),
				'is_global_ban': policy.geofencing.is_global_ban,
				'reason_code': policy.geofencing.reason.winning_source_id,
			}

		# 3. AI Rules Data
		if policy.ai_rules:
			bundle['ai_rules'] = {
				'training_allowed': policy.ai_rules.training_allowed,
				'fine_tuning_allowed': policy.ai_rules.fine_tuning_allowed,
				'rag_allowed': policy.ai_rules.rag_allowed,
				'attribution_required': policy.ai_rules.attribution_required,
				'attribution_text': policy.ai_rules.attribution_text,
				'reason_code': policy.ai_rules.reason.winning_source_id,
			}

		# 4. Purpose Data
		if policy.purpose:
			bundle['purpose'] = {
				'allowed_purposes': sorted(policy.purpose.allowed_purposes),
				'denied_purposes': sorted(policy.purpose.denied_purposes),
				'reason_code': policy.purpose.reason.winning_source_id,
			}

		# 5. Privacy Data
		if policy.privacy:
			bundle['privacy'] = {
				'method': policy.privacy.method.name,  # e.g. "PSEUDONYMIZATION"
				'parameters': policy.privacy.parameters,
				'reason_code': policy.privacy.reason.winning_source_id,
			}

		return bundle

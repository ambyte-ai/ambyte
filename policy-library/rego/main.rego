package ambyte.decision

import rego.v1

# ==============================================================================
# INPUT CONTRACT
# Expects standard Ambyte CheckRequest:
# {
#   "resource_urn": "urn:snowflake:prod:sales",
#   "action": "read",
#   "actor_id": "user_123",
#   "context": { "region": "US", "purpose": "MARKETING" }
# }
# ==============================================================================

# By default, we deny access unless explicitly allowed.
default allow := false

# Access is allowed if no denying constraints are triggered.
allow if {
	count(deny) == 0
}

# The target policy is retrieved from the generated data.json bundle.
target_policy := data.ambyte.policies[input.resource_urn]

# ==============================================================================
# 1. GEOFENCING (Space)
# ==============================================================================

# Global Ban
deny contains msg if {
	rule := target_policy.geofencing
	rule.is_global_ban == true
	msg := sprintf("Global Data Ban active (Source: %s)", [rule.reason_code])
}

# Missing Context (Fail Closed)
deny contains msg if {
	rule := target_policy.geofencing
	rule.is_global_ban == false
	not get_context_val(["region", "geo", "location", "country"])
	count(rule.allowed_regions) + count(rule.blocked_regions) > 0
	msg := "Context missing 'region' attribute required for geofencing."
}

# Explicitly Blocked
deny contains msg if {
	rule := target_policy.geofencing
	region := upper(get_context_val(["region", "geo", "location", "country"]))
	region in rule.blocked_regions
	msg := sprintf("Region '%s' is explicitly blocked.", [region])
}

# Not in Allowlist
deny contains msg if {
	rule := target_policy.geofencing
	count(rule.allowed_regions) > 0
	region := upper(get_context_val(["region", "geo", "location", "country"]))
	not region in rule.allowed_regions
	msg := sprintf("Region '%s' is not in the allowed list.", [region])
}

# ==============================================================================
# 2. PURPOSE LIMITATION (Intent)
# ==============================================================================

# Missing Context (Fail Closed)
deny contains msg if {
	rule := target_policy.purpose
	not get_context_val(["purpose", "intent", "usage"])
	count(rule.allowed_purposes) + count(rule.denied_purposes) > 0
	msg := "Context missing 'purpose' attribute."
}

# Explicitly Denied
deny contains msg if {
	rule := target_policy.purpose
	purpose := upper(get_context_val(["purpose", "intent", "usage"]))
	purpose in rule.denied_purposes
	msg := sprintf("Purpose '%s' is forbidden.", [purpose])
}

# Not in Allowlist
deny contains msg if {
	rule := target_policy.purpose
	count(rule.allowed_purposes) > 0
	purpose := upper(get_context_val(["purpose", "intent", "usage"]))
	not purpose in rule.allowed_purposes
	msg := sprintf("Purpose '%s' is not explicitly allowed.", [purpose])
}

# ==============================================================================
# 3. AI / ML RULES (Usage)
# ==============================================================================

deny contains msg if {
	rule := target_policy.ai_rules
	act := lower(input.action)
	contains(act, "train")
	rule.training_allowed == false
	msg := "AI Training is prohibited by policy."
}

deny contains msg if {
	rule := target_policy.ai_rules
	act := lower(input.action)
	contains(act, "fine")
	contains(act, "tune")
	rule.fine_tuning_allowed == false
	msg := "Model Fine-Tuning is prohibited by policy."
}

deny contains msg if {
	rule := target_policy.ai_rules
	act := lower(input.action)
	is_rag_action(act)
	rule.rag_allowed == false
	msg := "RAG/Retrieval usage is prohibited by policy."
}

is_rag_action(act) if contains(act, "rag")
is_rag_action(act) if contains(act, "retrieval")

# ==============================================================================
# 4. RETENTION (Time)
# ==============================================================================

deny contains msg if {
	rule := target_policy.retention
	rule.is_indefinite == false
	
	created_at := get_context_val(["created_at", "creation_date", "date"])
	created_at != null
	
	# Parse ISO8601 string to nanoseconds and calculate age
	created_ns := time.parse_rfc3339_ns(created_at)
	age_ns := time.now_ns() - created_ns
	max_ns := rule.max_seconds * 1000000000
	
	age_ns > max_ns
	
	# Calculate days for human-readable error message
	age_days := round(age_ns / (1000000000 * 60 * 60 * 24))
	max_days := round(max_ns / (1000000000 * 60 * 60 * 24))
	
	msg := sprintf("Data expired. Age %vd > Limit %vd.", [age_days, max_days])
}

# ==============================================================================
# 5. PRIVACY (Transformation)
# ==============================================================================

deny contains msg if {
	rule := target_policy.privacy
	rule.method != "UNSPECIFIED"
	
	fmt := lower(get_context_val(["output_format", "mode", "format"]))
	is_raw_format(fmt)
	
	msg := sprintf("Access Denied: Policy requires '%s', but '%s' output was requested.", [rule.method, fmt])
}

is_raw_format(fmt) if fmt == "raw"
is_raw_format(fmt) if fmt == "cleartext"
is_raw_format(fmt) if fmt == "unmasked"
is_raw_format(fmt) if fmt == "decrypt"


# ==============================================================================
# UTILITY HELPER
# ==============================================================================

# Helper to find a value in input.context using case-insensitive keys.
# Matches Python's `_get_context_val` heuristic.
get_context_val(keys) := val if {
	some k in keys
	some ctx_k, v in input.context
	lower(ctx_k) == lower(k)
	val := v
}
package rego.common

import future.keywords.if
import future.keywords.in

# ==============================================================================
# CONSTANTS
# ==============================================================================

# Rego works in nanoseconds for time.now_ns()
ns_per_sec := 1000000000
ns_per_hour := 3600 * ns_per_sec
ns_per_day := 24 * ns_per_hour

# ==============================================================================
# TIME & RETENTION LOGIC
# ==============================================================================

# Checks if a dataset has exceeded its retention period
# usage: is_expired(dataset.created_at_ns, 31536000) # 1 year in seconds
is_expired(creation_ts_ns, retention_seconds) if {
	age_ns := time.now_ns() - creation_ts_ns
	limit_ns := retention_seconds * ns_per_sec
	age_ns > limit_ns
}

# Returns the age of a resource in days
age_in_days(creation_ts_ns) := age if {
	diff := time.now_ns() - creation_ts_ns
	age := diff / ns_per_day
}

# Check if today is within a valid window (e.g., for "Business Hours Only" access)
is_business_hours if {
	# Get current time info
	ns := time.now_ns()
	day_of_week := time.weekday(ns) # Monday is "Monday"

	# Logic: Mon-Fri
	# If it is Sat/Sun, the rule fails here, saving the work of parsing the clock.
	day_of_week != "Saturday"
	day_of_week != "Sunday"

	# Logic: 9am - 5pm
	clock := time.clock(ns) # [hour, minute, second]
	hour := clock[0]
	hour >= 9
	hour < 17
}

# ==============================================================================
# SETS & LISTS (Permissions)
# ==============================================================================

# Returns true if two lists have ANY overlap
# Useful for: User Roles vs Allowed Roles
has_intersection(list_a, list_b) if {
	# Iterate over x in list_a, check if it exists in list_b
	some x in list_a
	x in list_b
}

# Returns true if ALL elements of required_list are in user_list
has_all(user_list, required_list) if {
	# Create a set of items that exist in BOTH lists,
	# then ensure the count matches the required list count.
	found := {x | some x in required_list; x in user_list}
	count(found) == count(required_list)
}

# ==============================================================================
# NETWORK & GEO (Geofencing)
# ==============================================================================

# Check if an IP address is inside a list of CIDR blocks
# usage: is_ip_allowed("192.168.1.5", ["192.168.1.0/24", "10.0.0.0/8"])
is_ip_in_cidrs(ip, cidr_list) if {
	some cidr in cidr_list
	net.cidr_contains(cidr, ip)
}

# Check if a region code is in the EU (Based on GDPR list)
# We hardcode the list here as a helper, though Ontology YAML is the source of truth.
is_eu_region(region_code) if {
	eu_codes := {
		"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
		"HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
		"SI", "ES", "SE",
	}

	# Use native lookup instead of helper
	region_code in eu_codes
}

# ==============================================================================
# RESOURCE MATCHING
# ==============================================================================

# Matches a resource URN against a glob pattern
# usage: matches_urn("urn:ambyte:snowflake:prod:sales:table1", "urn:ambyte:snowflake:prod:*:*")
matches_urn(urn, pattern) if {
	glob.match(pattern, [":"], urn)
}

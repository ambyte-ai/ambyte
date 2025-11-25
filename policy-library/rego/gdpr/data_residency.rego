package rego.gdpr

import rego.v1

import data.rego.common as utils

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Countries with "Adequacy Decisions" from the European Commission.
# These are treated as safe destinations even though they are not in the EU.
# Source: gdpr_mappings.yaml
adequate_countries := {
	"GB", # United Kingdom
	"CH", # Switzerland
	"JP", # Japan
	"CA", # Canada (Commercial organizations)
	"IL", # Israel
	"KR", # South Korea
	"NZ", # New Zealand
	"AR", # Argentina
	"UY", # Uruguay
	"AD", # Andorra
	"FO", # Faroe Islands
	"GG", # Guernsey
	"JE", # Jersey
	"IM", # Isle of Man
}

# ==============================================================================
# MAIN RULES
# ==============================================================================

# METADATA
# description: Default decision is to allow access unless explicitly denied.
# entrypoint: true
default allow := true

# METADATA
# description: Returns a set of reasons why access should be blocked based on GDPR residency rules.
# entrypoint: true
deny contains msg if {
	# 1. Scope: Only applies if the Dataset is legally resident in the EU/EEA
	utils.is_eu_region(input.dataset.geo_region)

	# 2. Trigger: The Actor (User/Service) or Destination is OUTSIDE the EU
	target_region := get_target_region(input)
	not utils.is_eu_region(target_region)

	# 3. Check: Is the destination on the Adequacy List?
	not adequate_countries[target_region]

	# 4. Exception: Check for US Data Privacy Framework (DPF) specific logic
	# If the target is US, we allow it ONLY if the actor claims DPF certification.
	not is_us_dpf_certified(target_region, input.actor)

	# 5. Conclusion: Block and report
	msg := sprintf(
		"GDPR Art. 44 Violation: Restricted transfer of EU data (%s) to non-adequate jurisdiction (%s).",
		[input.dataset.geo_region, target_region],
	)
}

# ==============================================================================
# HELPER LOGIC
# ==============================================================================

# Determine where the data is going.
# Priority:
# 1. Explicit Destination (e.g., "copy_job_target_region")
# 2. Actor Location Attribute (from LDAP/JWT)
# 3. Default to UNKNOWN (Block if unknown)
find_target_region(i) := region if {
	region := i.context.destination_region
} else := region if {
	# Safe lookup: input.actor.attributes["location"]
	# We use object.get to avoid crashing if 'attributes' is missing
	attrs := object.get(i.actor, "attributes", {})
	region := object.get(attrs, "location", "")
	region != ""
} else := "UNKNOWN"

# US Data Privacy Framework (DPF) Exception Logic.
# Returns true if:
# 1. The target is the US
# 2. The Actor has the specific "EU_US_DPF" certification in their attributes
is_us_dpf_certified(region, actor) if {
	region == "US"

	# Safely extract attributes map, default to empty object
	attrs := object.get(actor, "attributes", {})

	# Safely get the certification string
	# We handle cases where it might be a comma-separated list (e.g. "ISO27001,EU_US_DPF")
	cert_string := object.get(attrs, "compliance_certifications", "")

	# Check if our required cert is inside that string
	contains(cert_string, "EU_US_DPF")
}

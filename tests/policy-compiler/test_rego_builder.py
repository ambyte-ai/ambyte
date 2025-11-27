from datetime import timedelta

from ambyte_rules.models import (
	ConflictTrace,
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectiveRetention,
	ResolvedPolicy,
)
from policy_compiler.generators.rego_builder import RegoDataBuilder

# ==============================================================================
# HELPERS
# ==============================================================================


def make_trace(id_val: str) -> ConflictTrace:
	return ConflictTrace(
		winning_obligation_id=id_val, winning_source_id=f'Source-{id_val}', description='Test reasoning description.'
	)


# ==============================================================================
# TESTS
# ==============================================================================


def test_build_full_bundle_serialization():
	"""
	Verify that a fully populated ResolvedPolicy is correctly transformed
	into the dictionary structure expected by OPA.
	"""
	policy = ResolvedPolicy(
		resource_urn='urn:snowflake:prod:sales',
		# 1. Retention: Check timedelta -> seconds conversion
		retention=EffectiveRetention(
			duration=timedelta(days=1),  # 86400 seconds
			is_indefinite=False,
			reason=make_trace('RET-01'),
		),
		# 2. Geo: Check Set -> List conversion and sorting
		geofencing=EffectiveGeofencing(
			allowed_regions={'US', 'DE', 'FR'},  # Set order is random
			blocked_regions={'CN'},
			is_global_ban=False,
			reason=make_trace('GEO-01'),
		),
		# 3. AI: Check boolean flags
		ai_rules=EffectiveAiRules(
			training_allowed=False,
			fine_tuning_allowed=False,
			rag_allowed=True,
			attribution_required=True,
			attribution_text='MIT License',
			reason=make_trace('AI-01'),
		),
		contributing_obligation_ids=['RET-01', 'GEO-01', 'AI-01'],
	)

	builder = RegoDataBuilder()
	bundle = builder.build_bundle_data(policy)

	# General Metadata
	assert bundle['resource_urn'] == 'urn:snowflake:prod:sales'
	assert 'RET-01' in bundle['meta']['contributing_obligations']

	# Retention Assertions
	assert bundle['retention']['max_seconds'] == 86400
	assert bundle['retention']['reason_code'] == 'Source-RET-01'
	assert bundle['retention']['is_indefinite'] is False

	# Geo Assertions
	# Sets must be converted to lists for JSON, and sorted for determinism
	assert isinstance(bundle['geofencing']['allowed_regions'], list)
	assert bundle['geofencing']['allowed_regions'] == ['DE', 'FR', 'US']  # Sorted alpha
	assert bundle['geofencing']['blocked_regions'] == ['CN']

	# AI Assertions
	assert bundle['ai_rules']['training_allowed'] is False
	assert bundle['ai_rules']['rag_allowed'] is True
	assert bundle['ai_rules']['attribution_text'] == 'MIT License'


def test_build_partial_bundle():
	"""
	Verify behavior when only some constraints are present.
	Missing constraints should not appear in the JSON output to keep the bundle small.
	"""
	policy = ResolvedPolicy(
		resource_urn='urn:simple',
		# Only Geo is defined
		geofencing=EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace('GEO-99'), is_global_ban=False),
	)

	builder = RegoDataBuilder()
	bundle = builder.build_bundle_data(policy)

	assert 'geofencing' in bundle
	assert 'retention' not in bundle
	assert 'ai_rules' not in bundle

	assert bundle['geofencing']['allowed_regions'] == ['US']

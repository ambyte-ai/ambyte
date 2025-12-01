from datetime import timedelta

from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	PrivacyEnhancementRule,
	PrivacyMethod,
	PurposeRestriction,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)

# ==============================================================================
# HELPERS
# ==============================================================================


def make_provenance(id: str) -> SourceProvenance:
	return SourceProvenance(source_id=id, document_type='TEST', section_reference='1.0')


def make_obligation(id: str, constraint_arg: dict) -> Obligation:
	"""
	Helper to quickly spin up an Obligation with specific constraints.
	constraint_arg expects keys like 'retention', 'geofencing', or 'ai_model'.
	"""
	return Obligation(
		id=id,
		title=f'Test Obligation {id}',
		description='...',
		provenance=make_provenance(f'Source-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		**constraint_arg,
	)


# ==============================================================================
# RETENTION SOLVER TESTS
# ==============================================================================


def test_retention_shortest_period_wins():
	"""
	Scenario:
	- Contract A: Keep for 5 years (1825 days)
	- GDPR Policy: Keep for 2 years (730 days)
	- Result: 2 years (Strict minimization)
	"""
	ob1 = make_obligation(
		'1', {'retention': RetentionRule(duration=timedelta(days=1825), trigger=RetentionTrigger.CREATION_DATE)}
	)

	ob2 = make_obligation(
		'2', {'retention': RetentionRule(duration=timedelta(days=730), trigger=RetentionTrigger.CREATION_DATE)}
	)

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.retention is not None
	assert result.retention.duration == timedelta(days=730)
	# Ensure the trace points to the correct source
	assert result.retention.reason.winning_obligation_id == '2'
	assert 'shortest duration' in result.retention.reason.description


def test_retention_no_rules():
	"""Ensure it returns None if no retention rules exist."""
	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [])
	assert result.retention is None


# ==============================================================================
# GEO SOLVER TESTS
# ==============================================================================


def test_geo_intersection_logic():
	"""
	Scenario:
	- Rule 1: Allow [US, EU, CA]
	- Rule 2: Allow [EU, UK]
	- Result: [EU] (The only region common to both)
	"""
	ob1 = make_obligation('1', {'geofencing': GeofencingRule(allowed_regions=['US', 'EU', 'CA'])})

	ob2 = make_obligation('2', {'geofencing': GeofencingRule(allowed_regions=['EU', 'GB'])})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.geofencing is not None
	assert result.geofencing.allowed_regions == {'EU'}
	assert result.geofencing.is_global_ban is False


def test_geo_explicit_deny_trumps_allow():
	"""
	Scenario:
	- Rule 1: Allow [US, CN]
	- Rule 2: Deny [CN]
	- Result: [US]
	"""
	ob1 = make_obligation('1', {'geofencing': GeofencingRule(allowed_regions=['US', 'CN'])})

	ob2 = make_obligation('2', {'geofencing': GeofencingRule(denied_regions=['CN'])})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.geofencing is not None
	assert result.geofencing.allowed_regions == {'US'}
	assert 'CN' in result.geofencing.blocked_regions


def test_geo_global_ban():
	"""
	Scenario: Intersection is empty.
	- Rule 1: Allow [US]
	- Rule 2: Allow [EU]
	- Result: Global Ban
	"""
	ob1 = make_obligation('1', {'geofencing': GeofencingRule(allowed_regions=['US'])})
	ob2 = make_obligation('2', {'geofencing': GeofencingRule(allowed_regions=['EU'])})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.geofencing.is_global_ban is True
	assert len(result.geofencing.allowed_regions) == 0


# ==============================================================================
# AI SOLVER TESTS
# ==============================================================================


def test_ai_restrictive_and():
	"""
	Scenario:
	- Rule 1: Training Allowed = True
	- Rule 2: Training Allowed = False
	- Result: False
	"""
	ob1 = make_obligation('1', {'ai_model': AiModelConstraint(training_allowed=True)})
	ob2 = make_obligation('2', {'ai_model': AiModelConstraint(training_allowed=False)})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.ai_rules is not None
	assert result.ai_rules.training_allowed is False
	# The 'No' rule should be the winner/reason
	assert result.ai_rules.reason.winning_obligation_id == '2'


def test_ai_attribution_aggregation():
	"""
	Scenario:
	- Rule 1: Require "Copyright 2024"
	- Rule 2: Require "MIT License"
	- Result: Both texts combined.
	"""
	ob1 = make_obligation('1', {'ai_model': AiModelConstraint(attribution_text_required='Copyright 2024')})
	ob2 = make_obligation('2', {'ai_model': AiModelConstraint(attribution_text_required='MIT License')})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.ai_rules.attribution_required is True
	# Order isn't strictly guaranteed by list iteration unless sorted,
	# but we check both exist.
	assert 'Copyright 2024' in result.ai_rules.attribution_text
	assert 'MIT License' in result.ai_rules.attribution_text


# ==============================================================================
# PURPOSE SOLVER TESTS
# ==============================================================================


def test_purpose_intersection():
	"""
	Scenario:
	- Rule 1: Allow [ANALYTICS, MARKETING, SALES]
	- Rule 2: Allow [ANALYTICS, HR]
	- Result: [ANALYTICS] (Intersection)
	"""
	ob1 = make_obligation('1', {'purpose': PurposeRestriction(allowed_purposes=['ANALYTICS', 'MARKETING', 'SALES'])})
	ob2 = make_obligation('2', {'purpose': PurposeRestriction(allowed_purposes=['ANALYTICS', 'HR'])})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.purpose is not None
	assert result.purpose.allowed_purposes == {'ANALYTICS'}
	assert result.purpose.reason.winning_obligation_id == '2'


def test_purpose_denial_union():
	"""
	Scenario:
	- Rule 1: Deny [SALES]
	- Rule 2: Deny [HR]
	- Result: Denied [SALES, HR]
	"""
	ob1 = make_obligation('1', {'purpose': PurposeRestriction(denied_purposes=['SALES'])})
	ob2 = make_obligation('2', {'purpose': PurposeRestriction(denied_purposes=['HR'])})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.purpose is not None
	assert result.purpose.denied_purposes == {'SALES', 'HR'}


# ==============================================================================
# PRIVACY SOLVER TESTS
# ==============================================================================


def test_privacy_hierarchy():
	"""
	Scenario:
	- Rule 1: PSEUDONYMIZATION
	- Rule 2: ANONYMIZATION (Higher enum value)
	- Result: ANONYMIZATION
	"""
	ob1 = make_obligation('1', {'privacy': PrivacyEnhancementRule(method=PrivacyMethod.PSEUDONYMIZATION)})
	ob2 = make_obligation('2', {'privacy': PrivacyEnhancementRule(method=PrivacyMethod.ANONYMIZATION)})

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.privacy is not None
	assert result.privacy.method == PrivacyMethod.ANONYMIZATION
	assert result.privacy.reason.winning_obligation_id == '2'


def test_privacy_parameter_merge():
	"""
	Scenario: Differential Privacy Epsilon
	- Rule 1: Epsilon = 1.0
	- Rule 2: Epsilon = 0.5 (Stricter/Lower)
	- Result: Epsilon = 0.5
	"""
	ob1 = make_obligation(
		'1',
		{'privacy': PrivacyEnhancementRule(method=PrivacyMethod.DIFFERENTIAL_PRIVACY, parameters={'epsilon': '1.0'})},
	)
	ob2 = make_obligation(
		'2',
		{'privacy': PrivacyEnhancementRule(method=PrivacyMethod.DIFFERENTIAL_PRIVACY, parameters={'epsilon': '0.5'})},
	)

	engine = ConflictResolutionEngine()
	result = engine.resolve('urn:test', [ob1, ob2])

	assert result.privacy.method == PrivacyMethod.DIFFERENTIAL_PRIVACY
	# Should pick minimum float value
	assert result.privacy.parameters['epsilon'] == '0.5'


# ==============================================================================
# ENGINE INTEGRATION
# ==============================================================================


def test_engine_mixed_obligations():
	"""
	Verify the engine can process a list containing DIFFERENT types of obligations
	simultaneously and map them to the correct fields in ResolvedPolicy.
	"""
	# 1. Retention Rule
	ob_ret = make_obligation('ret', {'retention': RetentionRule(duration=timedelta(days=100), trigger=1)})

	# 2. Geo Rule
	ob_geo = make_obligation('geo', {'geofencing': GeofencingRule(allowed_regions=['US'])})

	# 3. Purpose Rule (New)
	ob_pur = make_obligation('pur', {'purpose': PurposeRestriction(denied_purposes=['SPAM'])})

	engine = ConflictResolutionEngine()
	# Pass mixed list
	result = engine.resolve('urn:snowflake:test', [ob_ret, ob_geo, ob_pur])

	assert isinstance(result, ResolvedPolicy)
	assert result.resource_urn == 'urn:snowflake:test'

	# Check Retention
	assert result.retention is not None
	assert result.retention.duration == timedelta(days=100)

	# Check Geo
	assert result.geofencing is not None
	assert result.geofencing.allowed_regions == {'US'}

	# Check Purpose
	assert result.purpose is not None
	assert 'SPAM' in result.purpose.denied_purposes

	# Check AI (Should be None as no AI rules passed)
	assert result.ai_rules is None

	# Check Audit Trail
	assert 'ret' in result.contributing_obligation_ids
	assert 'geo' in result.contributing_obligation_ids
	assert 'pur' in result.contributing_obligation_ids

"""
tests/python_sdk/test_evaluator.py
Tests the pure Python policy evaluation logic used by the SDK.
"""

from datetime import datetime, timedelta, timezone

import pytest
from ambyte.core.evaluator import LocalPolicyEvaluator
from ambyte_rules.models import (
	ConflictTrace,
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePrivacy,
	EffectivePurpose,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import PrivacyMethod

# ==============================================================================
# FIXTURES & HELPERS
# ==============================================================================


@pytest.fixture
def evaluator():
	return LocalPolicyEvaluator()


def make_trace():
	return ConflictTrace(winning_obligation_id='obl-1', winning_source_id='GDPR', description='Test reason')


def make_policy(**kwargs):
	"""Helper to create a ResolvedPolicy with specific active constraints."""
	defaults = {
		'resource_urn': 'urn:test',
		'contributing_obligation_ids': [],
		'retention': None,
		'geofencing': None,
		'ai_rules': None,
		'purpose': None,
		'privacy': None,
	}
	defaults.update(kwargs)
	return ResolvedPolicy(**defaults)


# ==============================================================================
# GEOFENCING TESTS
# ==============================================================================


def test_geo_global_ban(evaluator):
	"""Test explicit global ban."""
	geo = EffectiveGeofencing(is_global_ban=True, reason=make_trace())
	policy = make_policy(geofencing=geo)

	# Denials bubble up from evaluate()
	allowed, reason = evaluator.evaluate(policy, 'read', {'region': 'US'})
	assert allowed is False
	assert 'Global Data Ban' in reason


def test_geo_missing_context_fail_closed(evaluator):
	"""If restrictions exist but context is missing, it should fail closed."""
	geo = EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace())
	policy = make_policy(geofencing=geo)

	allowed, reason = evaluator.evaluate(policy, 'read', {'user': 'alice'})
	assert allowed is False
	assert 'Context missing' in reason


def test_geo_no_restrictions_missing_context_pass(evaluator):
	"""If geofencing object exists but lists are empty (and no global ban), it allows."""
	geo = EffectiveGeofencing(is_global_ban=False, reason=make_trace())

	# Test internal logic for specific reason
	allowed, reason = evaluator._check_geo(geo, {})
	assert allowed is True
	assert 'No specific geo' in reason

	# Test integration
	policy = make_policy(geofencing=geo)
	allowed_main, reason_main = evaluator.evaluate(policy, 'read', {})
	assert allowed_main is True
	assert reason_main == 'Access Allowed'


def test_geo_blocked_region(evaluator):
	"""Test explicit blocklist."""
	geo = EffectiveGeofencing(blocked_regions={'CN'}, reason=make_trace())
	policy = make_policy(geofencing=geo)

	allowed, reason = evaluator.evaluate(policy, 'read', {'region': 'cn'})  # Lowercase input
	assert allowed is False
	assert 'explicitly blocked' in reason


def test_geo_allowed_region_mismatch(evaluator):
	"""Test strict allowlist mismatch."""
	geo = EffectiveGeofencing(allowed_regions={'US', 'CA'}, reason=make_trace())
	policy = make_policy(geofencing=geo)

	allowed, reason = evaluator.evaluate(policy, 'read', {'region': 'DE'})
	assert allowed is False
	assert 'not in the allowed list' in reason


def test_geo_allowed_region_match(evaluator):
	"""Test allowlist success."""
	geo = EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace())

	# Internal check
	allowed, reason = evaluator._check_geo(geo, {'location': 'US'})
	assert allowed is True
	assert 'Region allowed' in reason


# ==============================================================================
# PURPOSE TESTS
# ==============================================================================


def test_purpose_missing_context_fail_closed(evaluator):
	"""If purpose rules exist but context is missing, fail."""
	pur = EffectivePurpose(allowed_purposes={'ANALYTICS'}, reason=make_trace())
	policy = make_policy(purpose=pur)

	allowed, reason = evaluator.evaluate(policy, 'read', {})
	assert allowed is False
	assert 'Context missing' in reason


def test_purpose_denied(evaluator):
	"""Test denied list."""
	pur = EffectivePurpose(denied_purposes={'MARKETING'}, reason=make_trace())
	policy = make_policy(purpose=pur)

	allowed, reason = evaluator.evaluate(policy, 'read', {'purpose': 'MARKETING'})
	assert allowed is False
	assert 'forbidden' in reason


def test_purpose_not_allowed(evaluator):
	"""Test allowlist exclusion."""
	pur = EffectivePurpose(allowed_purposes={'HR'}, reason=make_trace())
	policy = make_policy(purpose=pur)

	allowed, reason = evaluator.evaluate(policy, 'read', {'intent': 'SALES'})
	assert allowed is False
	assert 'not explicitly allowed' in reason


def test_purpose_success(evaluator):
	"""Test allowlist success."""
	pur = EffectivePurpose(allowed_purposes={'HR'}, reason=make_trace())

	# Internal check
	allowed, reason = evaluator._check_purpose(pur, {'usage': 'hr'})
	assert allowed is True
	assert 'Purpose allowed' in reason


# ==============================================================================
# AI TESTS
# ==============================================================================


def test_ai_training_blocked(evaluator):
	ai = EffectiveAiRules(training_allowed=False, reason=make_trace())
	policy = make_policy(ai_rules=ai)

	allowed, reason = evaluator.evaluate(policy, 'start_training_job', {})
	assert allowed is False
	assert 'Training is prohibited' in reason


def test_ai_finetuning_blocked(evaluator):
	ai = EffectiveAiRules(fine_tuning_allowed=False, reason=make_trace())
	policy = make_policy(ai_rules=ai)

	allowed, reason = evaluator.evaluate(policy, 'fine_tune_model', {})
	assert allowed is False
	assert 'Fine-Tuning is prohibited' in reason


def test_ai_rag_blocked(evaluator):
	ai = EffectiveAiRules(rag_allowed=False, reason=make_trace())
	policy = make_policy(ai_rules=ai)

	allowed, reason = evaluator.evaluate(policy, 'rag_retrieval', {})
	assert allowed is False
	assert 'RAG/Retrieval usage is prohibited' in reason


def test_ai_other_action_allowed(evaluator):
	"""Unknown AI actions (like 'view_metadata') should pass if not explicitly mapped."""
	ai = EffectiveAiRules(training_allowed=False, reason=make_trace())

	# Internal check
	allowed, reason = evaluator._check_ai(ai, 'view_dashboard')
	assert allowed is True
	assert 'AI action allowed' in reason


# ==============================================================================
# RETENTION TESTS
# ==============================================================================


def test_retention_indefinite_hold(evaluator):
	"""Legal hold overrides expiration."""
	ret = EffectiveRetention(duration=timedelta(days=1), is_indefinite=True, reason=make_trace())

	old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()

	# Internal check
	allowed, reason = evaluator._check_retention(ret, {'created_at': old_date})
	assert allowed is True
	assert 'Legal Hold' in reason


def test_retention_missing_date_fail_open(evaluator):
	"""If we don't know the date, we warn and allow (Fail Open logic)."""
	ret = EffectiveRetention(duration=timedelta(days=1), reason=make_trace())

	# Internal check
	allowed, reason = evaluator._check_retention(ret, {})  # No created_at
	assert allowed is True
	assert 'Missing Metadata' in reason


def test_retention_expired(evaluator):
	"""Data older than duration is blocked."""
	ret = EffectiveRetention(duration=timedelta(days=30), reason=make_trace())
	policy = make_policy(retention=ret)

	# Created 31 days ago
	past = datetime.now(timezone.utc) - timedelta(days=31)

	allowed, reason = evaluator.evaluate(policy, 'read', {'created_at': past.isoformat()})
	assert allowed is False
	assert 'Data expired' in reason


def test_retention_valid(evaluator):
	"""Data younger than duration is allowed."""
	ret = EffectiveRetention(duration=timedelta(days=30), reason=make_trace())

	# Created 1 day ago
	past = datetime.now(timezone.utc) - timedelta(days=1)

	# Internal Check
	allowed, reason = evaluator._check_retention(ret, {'created_at': past})
	assert allowed is True
	assert 'Retention valid' in reason


def test_retention_bad_date_format(evaluator):
	"""
	Invalid date format strings (e.g. 'not-a-date') raise ValueError in fromisoformat.
	This triggers the 'except Exception' block.
	"""
	ret = EffectiveRetention(duration=timedelta(days=1), reason=make_trace())

	# Internal check
	allowed, reason = evaluator._check_retention(ret, {'created_at': 'not-a-date'})
	assert allowed is True
	assert 'Skipped (Error)' in reason


def test_retention_naive_datetime_handling(evaluator):
	"""Ensure naive datetimes are forced to UTC for comparison."""
	ret = EffectiveRetention(duration=timedelta(hours=1), reason=make_trace())
	policy = make_policy(retention=ret)

	# Naive datetime 2 hours ago
	naive_past = datetime.now() - timedelta(hours=2)

	# This implies local time, evaluator should treat as UTC or local context
	allowed, reason = evaluator.evaluate(policy, 'read', {'created_at': naive_past})
	assert allowed is False
	assert 'Data expired' in reason


def test_retention_invalid_type_fail_open(evaluator):
	"""
	Ensure objects that are neither str nor datetime hit the explicit validation check
	and fail open with a specific message.
	"""
	ret = EffectiveRetention(duration=timedelta(days=1), reason=make_trace())

	class BadDate:
		pass

	allowed, reason = evaluator._check_retention(ret, {'created_at': BadDate()})
	assert allowed is True
	assert 'Skipped (Invalid Date Format)' in reason


# ==============================================================================
# PRIVACY TESTS
# ==============================================================================


def test_privacy_passthrough(evaluator):
	"""Privacy rules are currently advisory/passthrough in the SDK."""
	priv = EffectivePrivacy(method=PrivacyMethod.ANONYMIZATION, reason=make_trace())
	policy = make_policy(privacy=priv)

	allowed, reason = evaluator.evaluate(policy, 'read', {})
	assert allowed is True
	assert reason == 'Access Allowed'


# ==============================================================================
# ORCHESTRATION / PRIORITY TESTS
# ==============================================================================


def test_evaluation_short_circuit(evaluator):
	"""
	Ensure the evaluator stops at the first failure.
	Order: Geo -> Purpose -> AI -> Retention
	"""
	# Create a policy that fails Geo AND Retention
	geo = EffectiveGeofencing(blocked_regions={'US'}, reason=make_trace())
	ret = EffectiveRetention(duration=timedelta(days=1), reason=make_trace())

	policy = make_policy(geofencing=geo, retention=ret)

	# Context implies failure for both
	ctx = {'region': 'US', 'created_at': (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()}

	allowed, reason = evaluator.evaluate(policy, 'read', ctx)
	assert allowed is False

	# Should report Geo error, not Retention error (Geo is checked first)
	assert 'explicitly blocked' in reason
	assert 'expired' not in reason


def test_get_context_val_priority(evaluator):
	"""Verify context key lookup priority."""
	ctx = {'geo': 'US', 'Region': 'CA'}  # Mixed case, different keys

	# Should find 'Region' via case-insensitive lookup or direct key search logic
	val = evaluator._get_context_val(ctx, ['region'])
	assert val == 'CA'

	# Should find 'geo' if region missing
	val2 = evaluator._get_context_val({'geo': 'US'}, ['region', 'geo'])
	assert val2 == 'US'

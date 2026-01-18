from datetime import timedelta

from ambyte_compiler.diff_engine.models import ChangeImpact, ChangeType
from ambyte_compiler.diff_engine.service import SemanticDiffEngine
from ambyte_rules.models import ConflictTrace, EffectiveAiRules, EffectiveGeofencing, EffectiveRetention, ResolvedPolicy
from ambyte_schemas.models.obligation import RetentionTrigger


def make_trace():
	return ConflictTrace(winning_obligation_id='1', winning_source_id='A', description='B')


# --- RETENTION TESTS ---


def test_retention_diff_restrictive_duration():
	"""Test that reducing retention duration is Restrictive."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=365),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=30),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert report.has_changes
	item = report.changes[0]
	assert item.category == 'Retention'
	assert item.impact == ChangeImpact.RESTRICTIVE
	assert item.field == 'duration'


def test_retention_diff_permissive_duration():
	"""Test that increasing retention duration is Permissive."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=30),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=365),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert report.changes[0].impact == ChangeImpact.PERMISSIVE


def test_retention_removed():
	"""Test removing retention completely (defined -> None) is Permissive."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=30),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)
	new = ResolvedPolicy(resource_urn='urn:test', retention=None)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.change_type == ChangeType.REMOVED
	assert item.impact == ChangeImpact.PERMISSIVE


def test_retention_added():
	"""Test adding retention (None -> defined) is Restrictive."""
	old = ResolvedPolicy(resource_urn='urn:test', retention=None)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=1), reason=make_trace(), is_indefinite=False, trigger=RetentionTrigger.CREATION_DATE
		),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.change_type == ChangeType.ADDED
	assert item.impact == ChangeImpact.RESTRICTIVE


def test_retention_indefinite_flag():
	"""Test toggling the is_indefinite flag."""
	# Case A: False -> True (Permissive)
	old = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=30),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=30), reason=make_trace(), is_indefinite=True, trigger=RetentionTrigger.CREATION_DATE
		),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)
	assert report.changes[0].field == 'is_indefinite'
	assert report.changes[0].impact == ChangeImpact.PERMISSIVE

	# Case B: True -> False (Restrictive)
	# We swap arguments here to test the reverse
	report_reverse = engine.compute_diff(new, old)  # pylint: disable=arguments-out-of-order
	assert report_reverse.changes[0].impact == ChangeImpact.RESTRICTIVE


# --- GEOFENCING TESTS ---


def test_geo_added():
	"""Test adding geofencing rules where none existed."""
	old = ResolvedPolicy(resource_urn='urn:test', geofencing=None)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace(), is_global_ban=False),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.change_type == ChangeType.ADDED
	assert item.impact == ChangeImpact.RESTRICTIVE
	assert item.new_value == 'Defined'


def test_geo_diff_permissive_region_added():
	"""Test that adding a region to the set is Permissive."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace(), is_global_ban=False),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions={'US', 'DE'}, reason=make_trace(), is_global_ban=False),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.impact == ChangeImpact.PERMISSIVE
	assert item.new_value == ['DE']  # Only added showing


def test_geo_diff_restrictive_region_removed():
	"""Test that removing a region is Restrictive."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions={'US', 'DE'}, reason=make_trace(), is_global_ban=False),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace(), is_global_ban=False),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.impact == ChangeImpact.RESTRICTIVE
	assert item.old_value == ['DE']


def test_geo_global_ban_toggle():
	"""Test toggling global ban."""
	old = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions=set(), reason=make_trace(), is_global_ban=False),
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		geofencing=EffectiveGeofencing(allowed_regions=set(), reason=make_trace(), is_global_ban=True),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert report.changes[0].field == 'is_global_ban'
	assert report.changes[0].impact == ChangeImpact.RESTRICTIVE
	assert report.changes[0].new_value is True


# --- AI RULES TESTS ---


def make_ai_rules(training=False, fine_tuning=False, rag=False, attribution=False, text=''):
	return EffectiveAiRules(
		training_allowed=training,
		fine_tuning_allowed=fine_tuning,
		rag_allowed=rag,
		attribution_required=attribution,
		attribution_text=text,
		reason=make_trace(),
	)


def test_ai_bool_changes_permissive():
	"""Test standard boolean flips (False -> True = Permissive)."""
	old = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(training=False))
	new = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(training=True))

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert report.changes[0].category == 'AI Rules'
	assert report.changes[0].field == 'training_allowed'
	assert report.changes[0].impact == ChangeImpact.PERMISSIVE


def test_ai_attribution_restrictive():
	"""Test reverse boolean logic (Attribution Required: False -> True = Restrictive)."""
	old = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(attribution=False))
	new = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(attribution=True))

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.field == 'attribution_required'
	assert item.impact == ChangeImpact.RESTRICTIVE
	assert item.new_value is True


def test_ai_attribution_text_neutral():
	"""Test that changing attribution text is Neutral."""
	old = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(text='Copyright 2023'))
	new = ResolvedPolicy(resource_urn='urn:test', ai_rules=make_ai_rules(text='Copyright 2024'))

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	item = report.changes[0]
	assert item.field == 'attribution_text'
	assert item.impact == ChangeImpact.NEUTRAL


def test_ai_no_change():
	"""Test when old and new AI rules are identical."""
	rules = make_ai_rules(training=True)
	old = ResolvedPolicy(resource_urn='urn:test', ai_rules=rules)
	new = ResolvedPolicy(resource_urn='urn:test', ai_rules=rules)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)
	assert not report.has_changes


# --- REPORTING TESTS ---


def test_no_changes_detected():
	"""Test processing identical policies."""
	old = ResolvedPolicy(resource_urn='urn:test', retention=None, geofencing=None, ai_rules=None)
	new = ResolvedPolicy(resource_urn='urn:test', retention=None, geofencing=None, ai_rules=None)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert not report.has_changes
	assert 'No Material Changes' in report.to_markdown()


def test_markdown_risk_increase():
	"""Test markdown generation for increased risk."""
	old = ResolvedPolicy(resource_urn='urn:test', retention=None)
	new = ResolvedPolicy(resource_urn='urn:test', retention=None)
	# Simulate a permissive change manually to check report logic
	# (Using real objects usually, but checking Report class logic here)
	engine = SemanticDiffEngine()

	# We trigger a permissive change via Geo logic
	old.geofencing = EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace(), is_global_ban=False)
	new.geofencing = EffectiveGeofencing(allowed_regions={'US', 'EU'}, reason=make_trace(), is_global_ban=False)

	report = engine.compute_diff(old, new)
	md = report.to_markdown()

	assert 'Risk Profile Increased' in md
	assert '(+1)' in md


def test_markdown_risk_decrease():
	"""Test markdown generation for decreased risk."""
	old = ResolvedPolicy(resource_urn='urn:test', retention=None)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		retention=EffectiveRetention(
			duration=timedelta(days=1), reason=make_trace(), is_indefinite=False, trigger=RetentionTrigger.CREATION_DATE
		),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	md = report.to_markdown()
	assert 'Risk Profile Decreased' in md
	assert 'Retention rule added' in md


def test_markdown_risk_neutral():
	"""Test markdown generation for neutral risk (balanced or text only)."""
	# Create a scenario where one is strict and one is permissive
	old = ResolvedPolicy(
		resource_urn='urn:test',
		# Has short retention (strict)
		retention=EffectiveRetention(
			duration=timedelta(days=10),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
		# No geo
		geofencing=None,
	)
	new = ResolvedPolicy(
		resource_urn='urn:test',
		# Increased retention (permissive) -> +1
		retention=EffectiveRetention(
			duration=timedelta(days=100),
			reason=make_trace(),
			is_indefinite=False,
			trigger=RetentionTrigger.CREATION_DATE,
		),
		# Added geo (restrictive) -> -1
		geofencing=EffectiveGeofencing(allowed_regions={'US'}, reason=make_trace(), is_global_ban=False),
	)

	engine = SemanticDiffEngine()
	report = engine.compute_diff(old, new)

	assert report.risk_score_delta == 0
	md = report.to_markdown()
	assert 'Risk Profile Neutral' in md

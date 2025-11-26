from datetime import timedelta

from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	PrivacyEnhancementRule,
	PrivacyMethod,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)
from ambyte_schemas.proto.obligation.v1 import obligation_pb2

# ==============================================================================
# SUB-MODEL TESTS
# ==============================================================================


def test_retention_rule_model():
	"""Test timedelta handling in RetentionRule."""
	rule = RetentionRule(
		duration=timedelta(days=365), trigger=RetentionTrigger.CREATION_DATE, allow_legal_hold_override=True
	)

	# Check attributes
	assert rule.duration.days == 365
	assert rule.trigger == RetentionTrigger.CREATION_DATE

	# Check Proto Conversion
	proto = rule.to_proto()
	assert isinstance(proto, obligation_pb2.RetentionRule)
	# Protobuf Duration is in seconds
	assert proto.duration.seconds == 365 * 24 * 3600
	assert proto.trigger == obligation_pb2.RetentionRule.RETENTION_TRIGGER_CREATION_DATE


def test_geofencing_rule_lists():
	"""Test list handling for regions."""
	rule = GeofencingRule(allowed_regions=['US', 'CA'], denied_regions=['CN', 'RU'], strict_residency=True)

	proto = rule.to_proto()
	assert len(proto.allowed_regions) == 2
	assert 'US' in proto.allowed_regions
	assert proto.strict_residency is True

	reconstructed = GeofencingRule.from_proto(proto)
	assert reconstructed.allowed_regions == ['US', 'CA']
	assert reconstructed.denied_regions == ['CN', 'RU']


def test_privacy_enhancement_params():
	"""Test map/dict handling in Privacy rules."""
	rule = PrivacyEnhancementRule(
		method=PrivacyMethod.DIFFERENTIAL_PRIVACY, parameters={'epsilon': '0.5', 'delta': '1e-5'}
	)

	proto = rule.to_proto()
	assert proto.method == obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_DIFFERENTIAL_PRIVACY
	assert proto.parameters['epsilon'] == '0.5'

	reconstructed = PrivacyEnhancementRule.from_proto(proto)
	assert reconstructed.parameters == rule.parameters


# ==============================================================================
# OBLIGATION POLYMORPHISM (OneOf) TESTS
# ==============================================================================


def test_obligation_retention_roundtrip(sample_obligation_retention):
	"""
	Test a full roundtrip of an Obligation containing a RetentionRule.
	Uses the fixture from conftest.py.
	"""
	# 1. Pydantic -> Proto
	proto = sample_obligation_retention.to_proto()

	# 2. Verify Proto 'OneOf' selection
	# In Protobuf, 'WhichOneof' tells us which field is actually set
	assert proto.WhichOneof('constraint') == 'retention'
	assert proto.HasField('retention')
	assert not proto.HasField('geofencing')
	assert not proto.HasField('ai_model')

	# 3. Proto -> Pydantic
	reconstructed = Obligation.from_proto(proto)

	# 4. Verify Pydantic State
	# 'retention' should be populated, others should be None
	assert reconstructed.retention is not None
	assert isinstance(reconstructed.retention, RetentionRule)
	assert reconstructed.retention.duration == timedelta(days=365)

	assert reconstructed.geofencing is None
	assert reconstructed.ai_model is None
	assert reconstructed.privacy is None


def test_obligation_ai_constraint_roundtrip():
	"""Test roundtrip for AI Model constraints."""
	ai_rule = AiModelConstraint(
		training_allowed=False,
		fine_tuning_allowed=True,
		requires_open_source_release=True,
		attribution_text_required='CC-BY-SA',
	)

	obl = Obligation(
		id='ai_act_high_risk',
		title='AI Transparency',
		description='Must attribute source.',
		provenance=SourceProvenance(source_id='AI-ACT', document_type='REGULATION'),
		enforcement_level=EnforcementLevel.NOTIFY_HUMAN,
		ai_model=ai_rule,  # Setting this specific field
	)

	# To Proto
	proto = obl.to_proto()
	assert proto.WhichOneof('constraint') == 'ai_model'
	assert proto.ai_model.attribution_text_required == 'CC-BY-SA'

	# From Proto
	reconstructed = Obligation.from_proto(proto)
	assert reconstructed.ai_model is not None
	assert reconstructed.retention is None
	assert reconstructed.ai_model.training_allowed is False


def test_obligation_priority_handling():
	"""
	EDGE CASE: What happens if a developer accidentally sets TWO constraints
	on the Pydantic model?

	The implementation of `to_proto` uses an if/elif chain.
	We verify the priority order ensures deterministic Protobuf generation.
	"""
	retention = RetentionRule(duration=timedelta(days=1), trigger=RetentionTrigger.CREATION_DATE)
	geofencing = GeofencingRule(allowed_regions=['US'])

	# Technically invalid logically, but valid in Python object structure
	obl = Obligation(
		id='conflict_test',
		title='Conflict',
		description='...',
		provenance=SourceProvenance(source_id='X', document_type='TEST'),
		retention=retention,
		geofencing=geofencing,  # Accidental double assignment
	)

	# 1. Convert to Proto
	proto = obl.to_proto()

	# 2. Verify behavior
	# Based on the implementation in obligation.py:
	# if self.retention: ... elif self.geofencing: ...
	# Retention checks come first.
	assert proto.WhichOneof('constraint') == 'retention'
	assert proto.HasField('retention')

	# Geofencing data is effectively discarded during serialization
	# because Protobuf OneOf can only hold one value.
	assert not proto.HasField('geofencing')


def test_enforcement_level_enum():
	"""Ensure top-level enums in Obligation map correctly."""
	obl = Obligation(
		id='test_enum',
		title='T',
		description='D',
		provenance=SourceProvenance(source_id='S', document_type='D'),
		enforcement_level=EnforcementLevel.AUDIT_ONLY,
	)

	proto = obl.to_proto()
	assert proto.enforcement_level == obligation_pb2.ENFORCEMENT_LEVEL_AUDIT_ONLY

	# Check default
	obl_default = Obligation(
		id='test_def', title='T', description='D', provenance=SourceProvenance(source_id='S', document_type='D')
	)

	assert obl_default.enforcement_level == EnforcementLevel.AUDIT_ONLY

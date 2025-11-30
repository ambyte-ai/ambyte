from datetime import datetime, timedelta, timezone

import pytest
from ambyte_schemas.models.common import (
	Actor,
	ActorType,
	ResourceIdentifier,
	RiskSeverity,
	SensitivityLevel,
)
from ambyte_schemas.models.dataset import (
	Dataset,
	DataSubjectType,
	LicenseInfo,
	PiiCategory,
	SchemaField,
)
from ambyte_schemas.models.lineage import (
	ModelArtifact,
	ModelType,
	Run,
	RunType,
)
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
# HELPER FIXTURES
# ==============================================================================


@pytest.fixture
def utc_now():
	"""Returns a timezone-aware UTC datetime (microsecond precision)."""
	return datetime.now(timezone.utc)


@pytest.fixture
def base_actor():
	return Actor(
		id='user_test_001',
		type=ActorType.HUMAN,
		roles=['admin', 'editor'],
		attributes={'department': 'engineering', 'clearance': 'L5'},
	)


@pytest.fixture
def base_provenance():
	return SourceProvenance(
		source_id='GDPR-ART-17',
		document_type='REGULATION',
		section_reference='Para 1',
		document_uri='https://gdpr-info.eu/art-17-gdpr/',
	)


# ==============================================================================
# COMMON MODELS
# ==============================================================================


def test_actor_full_roundtrip(base_actor):
	"""Test Actor with roles (list) and attributes (map)."""
	# 1. Pydantic -> Proto
	proto = base_actor.to_proto()

	# Check List
	assert list(proto.roles) == ['admin', 'editor']
	# Check Map
	assert proto.attributes['department'] == 'engineering'
	# Check Enum
	assert proto.type == 1  # ACTOR_TYPE_HUMAN

	# 2. Proto -> Pydantic
	reconstructed = Actor.from_proto(proto)

	assert reconstructed.id == base_actor.id
	assert reconstructed.attributes == base_actor.attributes
	assert reconstructed.roles == base_actor.roles
	assert reconstructed.type == ActorType.HUMAN


def test_resource_identifier_roundtrip():
	res = ResourceIdentifier(platform='aws', location='us-east-1', native_id='arn:aws:s3:::bucket')

	reconstructed = ResourceIdentifier.from_proto(res.to_proto())
	assert reconstructed.model_dump() == res.model_dump()


# ==============================================================================
# DATASET MODELS (Complex Nesting & Time)
# ==============================================================================


def test_dataset_complex_roundtrip(base_actor, utc_now):
	"""
	Tests deep nesting: Dataset -> [SchemaField], Dataset -> LicenseInfo,
	Dataset -> Actor, plus Timestamps and Enums.
	"""
	dataset = Dataset(
		id='ds_123',
		urn='urn:ambyte:test:dataset',
		name='Complex Data',
		description='Testing roundtrip capabilities',
		owner=base_actor,
		resource=ResourceIdentifier(platform='snowflake', location='db.schema'),
		fields=[
			SchemaField(name='email', native_type='VARCHAR', is_pii=True, pii_category=PiiCategory.EMAIL_ADDRESS),
			SchemaField(name='age', native_type='INT'),
		],
		sensitivity=SensitivityLevel.RESTRICTED,
		geo_region='US',
		data_subjects=[DataSubjectType.EMPLOYEE, DataSubjectType.PATIENT],
		license=LicenseInfo(spdx_id='Proprietary', ai_training_allowed=False),
		created_at=utc_now,
		updated_at=utc_now + timedelta(hours=1),
	)

	# 1. To Proto
	proto = dataset.to_proto()

	# Assert specific conversions
	assert proto.fields[0].pii_category == PiiCategory.EMAIL_ADDRESS.value
	assert len(proto.data_subjects) == 2
	assert proto.owner.id == base_actor.id
	assert proto.created_at.seconds == int(utc_now.timestamp())

	# 2. From Proto
	reconstructed = Dataset.from_proto(proto)

	# 3. Equality Check
	# Note: We compare dictionaries to handle object identity,
	# and exclude 'updated_at' strict equality if microsecond precision drifts slightly
	# in protobuf serialization (though standard lib usually handles it well).
	orig_dump = dataset.model_dump(mode='json')
	new_dump = reconstructed.model_dump(mode='json')

	assert orig_dump == new_dump


def test_dataset_null_optionals():
	"""Test behavior when optional fields are None."""
	dataset = Dataset(
		id='minimal',
		urn='urn:min',
		name='Minimal',
		# Explicitly None
		owner=None,
		license=None,
		created_at=None,
	)

	proto = dataset.to_proto()
	assert not proto.HasField('owner')
	assert not proto.HasField('license')
	assert not proto.HasField('created_at')

	reconstructed = Dataset.from_proto(proto)
	assert reconstructed.owner is None
	assert reconstructed.license is None
	assert reconstructed.created_at is None


# ==============================================================================
# LINEAGE MODELS
# ==============================================================================


def test_lineage_run_roundtrip(base_actor, utc_now):
	run = Run(
		id='run_abc',
		type=RunType.AI_FINE_TUNING,
		triggered_by=base_actor,
		start_time=utc_now,
		end_time=utc_now + timedelta(minutes=10),
		success=True,
	)

	reconstructed = Run.from_proto(run.to_proto())
	assert reconstructed.type == RunType.AI_FINE_TUNING
	assert reconstructed.success is True
	assert reconstructed.end_time > reconstructed.start_time


def test_model_artifact_roundtrip():
	model = ModelArtifact(
		id='model_1',
		urn='urn:model:gpt4',
		name='GPT-4',
		version='v1',
		model_type=ModelType.LLM,
		risk_level=RiskSeverity.HIGH,
		base_model_urn='urn:model:base',
	)

	reconstructed = ModelArtifact.from_proto(model.to_proto())
	assert reconstructed.model_type == ModelType.LLM
	assert reconstructed.risk_level == RiskSeverity.HIGH


# ==============================================================================
# OBLIGATION POLYMORPHISM (The Hardest Part)
# ==============================================================================


@pytest.mark.parametrize(
	'constraint_type, constraint_obj, expected_check',
	[
		(
			'retention',
			RetentionRule(duration=timedelta(days=90), trigger=RetentionTrigger.CREATION_DATE),
			lambda x: x.duration == timedelta(days=90),
		),
		(
			'geofencing',
			GeofencingRule(allowed_regions=['US', 'CA'], strict_residency=True),
			lambda x: 'US' in x.allowed_regions and x.strict_residency is True,
		),
		(
			'purpose',
			PurposeRestriction(allowed_purposes=['ANALYTICS'], denied_purposes=['MARKETING']),
			lambda x: 'MARKETING' in x.denied_purposes,
		),
		(
			'privacy',
			PrivacyEnhancementRule(method=PrivacyMethod.DIFFERENTIAL_PRIVACY, parameters={'epsilon': '1.0'}),
			lambda x: x.method == PrivacyMethod.DIFFERENTIAL_PRIVACY and x.parameters['epsilon'] == '1.0',
		),
		(
			'ai_model',
			AiModelConstraint(training_allowed=False, attribution_text_required='CC-BY'),
			lambda x: x.training_allowed is False and x.attribution_text_required == 'CC-BY',
		),
	],
)
def test_obligation_oneof_roundtrip(base_provenance, constraint_type, constraint_obj, expected_check):
	"""
	Parametrized test to ensure EVERY type of constraint in the OneOf block
	round-trips correctly and doesn't bleed into other fields.
	"""
	# 1. Construct Obligation with dynamic keyword argument
	kwargs = {
		'id': f'test_{constraint_type}',
		'title': 'Test Policy',
		'description': '...',
		'provenance': base_provenance,
		'enforcement_level': EnforcementLevel.BLOCKING,
		constraint_type: constraint_obj,
	}

	obligation = Obligation(**kwargs)

	# 2. To Proto
	proto = obligation.to_proto()

	# Ensure the correct OneOf field is set in Protobuf
	assert proto.WhichOneof('constraint') == constraint_type

	# 3. Back to Pydantic
	reconstructed = Obligation.from_proto(proto)

	# 4. Verify the specific constraint matches logic
	active_constraint = getattr(reconstructed, constraint_type)
	assert active_constraint is not None
	assert expected_check(active_constraint)

	# 5. Verify other constraints are None
	all_types = ['retention', 'geofencing', 'purpose', 'privacy', 'ai_model']
	for other in all_types:
		if other != constraint_type:
			assert getattr(reconstructed, other) is None


def test_timedelta_duration_conversion():
	"""Specific check for Python timedelta -> Google Protobuf Duration."""
	# 1 day, 1 hour, 1 second
	td = timedelta(days=1, hours=1, seconds=1)
	expected_seconds = 86400 + 3600 + 1

	rule = RetentionRule(duration=td, trigger=RetentionTrigger.EVENT_DATE)
	proto = rule.to_proto()

	assert proto.duration.seconds == expected_seconds

	reconstructed = RetentionRule.from_proto(proto)
	assert reconstructed.duration == td

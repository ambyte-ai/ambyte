import pytest
from ambyte_schemas.models.common import (
	Actor,
	ActorType,
	ResourceIdentifier,
	RiskSeverity,
	SensitivityLevel,
	Tag,
)
from ambyte_schemas.proto.common.v1 import common_pb2
from pydantic import ValidationError

# ==============================================================================
# ENUM INTEGRITY TESTS
# ==============================================================================


@pytest.mark.parametrize(
	'enum_cls, proto_const, expected_int',
	[
		(SensitivityLevel, 'SENSITIVITY_LEVEL_PUBLIC', 1),
		(SensitivityLevel, 'SENSITIVITY_LEVEL_RESTRICTED', 4),
		(RiskSeverity, 'RISK_SEVERITY_HIGH', 3),
		(RiskSeverity, 'RISK_SEVERITY_UNACCEPTABLE', 4),
		(ActorType, 'ACTOR_TYPE_HUMAN', 1),
		(ActorType, 'ACTOR_TYPE_SERVICE_ACCOUNT', 2),
	],
)
def test_enum_mapping_integrity(enum_cls, proto_const, expected_int):
	"""
	Ensures that the Python Pydantic Enums map 1:1 to the Protobuf integer constants.
	"""
	# Handle Nested Enums (defined inside a Message) vs Top-Level Enums
	if enum_cls == ActorType:
		proto_val = getattr(common_pb2.Actor, proto_const)
	else:
		# Standard top-level enums
		proto_val = getattr(common_pb2, proto_const)

	assert proto_val == expected_int

	# Check that creating the Enum from the int works and matches
	assert enum_cls(expected_int).value == expected_int


def test_enum_instantiation():
	"""Test that we can instantiate models using ints or enum members."""
	# 1. Using Enum member
	a1 = Actor(id='1', type=ActorType.HUMAN)

	# NOTE: Because use_enum_values=True in AmbyteBaseModel,
	# the field is stored as the raw integer, not the Enum object.
	assert isinstance(a1.type, int)
	assert a1.type == 1

	# IntEnum allows comparison between the int and the Enum member
	assert a1.type == ActorType.HUMAN

	# 2. Using Integer directly (Pydantic allows this)
	a2 = Actor(id='2', type=1)  # type: ignore
	assert a2.type == ActorType.HUMAN


# ==============================================================================
# MODEL VALIDATION TESTS
# ==============================================================================


def test_tag_model():
	"""Test basic Tag behavior."""
	t = Tag(key='env', value='prod')
	assert t.key == 'env'
	assert t.value == 'prod'

	with pytest.raises(ValidationError):
		Tag(key='env')  # type: ignore # Missing value


def test_resource_identifier_defaults():
	"""Test ResourceIdentifier defaults."""
	r = ResourceIdentifier(platform='aws', location='bucket/path')
	assert r.native_id == ''
	assert r.platform == 'aws'


def test_actor_defaults():
	"""Test Actor defaults (empty lists/dicts)."""
	a = Actor(id='u123', type=ActorType.SERVICE_ACCOUNT)

	# Verify defaults
	assert a.roles == []
	assert a.attributes == {}

	# Verify assignments
	a.roles.append('admin')
	a.attributes['region'] = 'us-east-1'

	assert 'admin' in a.roles
	assert a.attributes['region'] == 'us-east-1'


# ==============================================================================
# PROTOBUF ROUND-TRIP TESTS
# ==============================================================================


def test_tag_proto_roundtrip():
	original = Tag(key='cost_center', value='101')

	# 1. To Proto
	proto_obj = original.to_proto()
	assert isinstance(proto_obj, common_pb2.Tag)
	assert proto_obj.key == 'cost_center'
	assert proto_obj.value == '101'

	# 2. From Proto
	reconstructed = Tag.from_proto(proto_obj)
	assert reconstructed == original


def test_resource_identifier_proto_roundtrip():
	original = ResourceIdentifier(platform='snowflake', location='db.schema.table', native_id='sf_guid_123')

	proto_obj = original.to_proto()
	assert isinstance(proto_obj, common_pb2.ResourceIdentifier)
	assert proto_obj.platform == 'snowflake'

	reconstructed = ResourceIdentifier.from_proto(proto_obj)
	assert reconstructed == original
	assert reconstructed.native_id == 'sf_guid_123'


def test_actor_proto_roundtrip():
	"""
	Test round-trip conversion for Actor, including the attributes map.
	"""
	original = Actor(
		id='auth0|123456',
		type=ActorType.HUMAN,
		roles=['ADMIN', 'EDITOR'],
		attributes={'location': 'EU', 'department': 'Engineering', 'security_clearance': 'L4'},
	)

	# 1. To Proto
	proto_obj = original.to_proto()
	assert isinstance(proto_obj, common_pb2.Actor)
	assert proto_obj.id == 'auth0|123456'
	assert proto_obj.type == common_pb2.Actor.ACTOR_TYPE_HUMAN

	# Verify Map Fields
	assert proto_obj.attributes['location'] == 'EU'
	assert proto_obj.attributes['security_clearance'] == 'L4'

	# 2. From Proto
	reconstructed = Actor.from_proto(proto_obj)

	assert reconstructed.id == original.id
	assert reconstructed.type == original.type
	assert reconstructed.roles == original.roles
	assert reconstructed.attributes == original.attributes

	# Full Equality check
	assert reconstructed == original

from ambyte_schemas.models.common import Actor, SensitivityLevel
from ambyte_schemas.models.dataset import Dataset, DataSubjectType, LicenseInfo, PiiCategory, SchemaField
from ambyte_schemas.proto.dataset.v1 import dataset_pb2


def test_schema_field_defaults():
	"""
	Test that SchemaField initializes with correct default values
	(e.g., is_pii=False, PiiCategory.NONE).
	"""
	field = SchemaField(name='user_id', native_type='INT')

	assert field.name == 'user_id'
	assert field.native_type == 'INT'
	assert field.is_pii is False
	assert field.pii_category == PiiCategory.NONE
	assert field.sensitivity == SensitivityLevel.UNSPECIFIED
	assert field.is_identifier is False


def test_schema_field_serialization():
	"""Test Pydantic serialization of a fully populated field."""
	field = SchemaField(
		name='email',
		native_type='VARCHAR(255)',
		is_pii=True,
		pii_category=PiiCategory.EMAIL_ADDRESS,
		sensitivity=SensitivityLevel.CONFIDENTIAL,
	)

	data = field.model_dump()
	assert data['is_pii'] is True
	assert data['pii_category'] == PiiCategory.EMAIL_ADDRESS.value


def test_license_info_model():
	"""Test LicenseInfo model creation."""
	lic = LicenseInfo(spdx_id='Apache-2.0', commercial_use_allowed=True, ai_training_allowed=True)
	assert lic.spdx_id == 'Apache-2.0'
	assert lic.ai_training_allowed is True
	# Check default
	assert lic.modification_allowed is False


def test_dataset_initialization(sample_dataset, sample_actor):
	"""
	Test that the sample_dataset fixture loads correctly and
	relationships (owner, fields) are objects, not just dicts.
	"""
	assert isinstance(sample_dataset, Dataset)
	assert sample_dataset.urn == 'urn:ambyte:snowflake:prod_db:sales:customers'

	# Check Relationship
	assert isinstance(sample_dataset.owner, Actor)
	assert sample_dataset.owner.id == sample_actor.id

	# Check List of Objects
	assert len(sample_dataset.fields) == 2
	assert isinstance(sample_dataset.fields[0], SchemaField)
	assert sample_dataset.fields[0].name == 'email'


def test_dataset_proto_conversion_explicit(sample_dataset):
	"""
	Test manual conversion to Protobuf to ensure fields map to the
	correct Protobuf indices/names.
	"""
	proto_obj = sample_dataset.to_proto()

	assert isinstance(proto_obj, dataset_pb2.Dataset)
	assert proto_obj.id == sample_dataset.id
	assert proto_obj.urn == sample_dataset.urn
	assert proto_obj.geo_region == 'DE'

	# Check Enum Integer Mapping
	assert proto_obj.sensitivity == SensitivityLevel.CONFIDENTIAL.value

	# Check Repeated Field (List)
	assert len(proto_obj.fields) == 2
	assert proto_obj.fields[0].pii_category == PiiCategory.EMAIL_ADDRESS.value

	# Check Timestamp Conversion
	# Protobuf stores seconds/nanos, we just check generic equality logic
	assert proto_obj.HasField('created_at')
	assert proto_obj.created_at.seconds > 0


def test_dataset_round_trip(sample_dataset):
	"""
	CRITICAL: Test Pydantic -> Protobuf -> Pydantic.
	This ensures no data loss occurs when sending objects over the wire.
	"""
	# 1. Convert to Proto
	proto_obj = sample_dataset.to_proto()

	# 2. Convert back to Pydantic
	reconstructed = Dataset.from_proto(proto_obj)

	# 3. Assert Equality
	# We compare dictionary dumps to handle object identity differences
	original_dump = sample_dataset.model_dump(mode='json')
	new_dump = reconstructed.model_dump(mode='json')

	# Note: Datetimes might have slight precision differences (microseconds)
	# depending on proto serialization, but usually exact equality holds
	# if using standard libraries.
	assert original_dump == new_dump


def test_dataset_optional_fields_none():
	"""
	Test serialization when optional fields (owner, license, timestamps) are None.
	Protobuf handles None by simply not setting the field (HasField returns False).
	"""
	ds = Dataset(id='minimal_1', urn='urn:minimal', name='Minimal Dataset', owner=None, resource=None, license=None)

	# Convert to Proto
	proto = ds.to_proto()

	assert not proto.HasField('owner')
	assert not proto.HasField('resource')
	assert not proto.HasField('license')
	assert not proto.HasField('created_at')

	# Convert back
	reconstructed = Dataset.from_proto(proto)
	assert reconstructed.owner is None
	assert reconstructed.license is None
	assert reconstructed.created_at is None


def test_data_subject_enum_list():
	"""Test handling of repeated Enum fields (list of integers)."""
	ds = Dataset(
		id='enum_test',
		urn='urn:enum',
		name='Enum Test',
		data_subjects=[DataSubjectType.CUSTOMER, DataSubjectType.EMPLOYEE],
	)

	proto = ds.to_proto()
	# In proto, this is a repeated int32
	assert len(proto.data_subjects) == 2
	assert proto.data_subjects[0] == DataSubjectType.CUSTOMER.value

	reconstructed = Dataset.from_proto(proto)
	assert reconstructed.data_subjects == [DataSubjectType.CUSTOMER, DataSubjectType.EMPLOYEE]

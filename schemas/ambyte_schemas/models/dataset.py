from datetime import datetime
from enum import IntEnum

from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import Field

from ambyte_schemas.models.common import (
	Actor,
	AmbyteBaseModel,
	ResourceIdentifier,
	SensitivityLevel,
)
from ambyte_schemas.proto.dataset.v1 import dataset_pb2

# ==============================================================================
# Enums
# ==============================================================================


class PiiCategory(IntEnum):
	UNSPECIFIED = dataset_pb2.PII_CATEGORY_UNSPECIFIED
	NONE = dataset_pb2.PII_CATEGORY_NONE
	EMAIL_ADDRESS = dataset_pb2.PII_CATEGORY_EMAIL_ADDRESS
	PHONE_NUMBER = dataset_pb2.PII_CATEGORY_PHONE_NUMBER
	FULL_NAME = dataset_pb2.PII_CATEGORY_FULL_NAME
	GOV_ID = dataset_pb2.PII_CATEGORY_GOV_ID
	IP_ADDRESS = dataset_pb2.PII_CATEGORY_IP_ADDRESS
	DEVICE_ID = dataset_pb2.PII_CATEGORY_DEVICE_ID
	GEOLOCATION_PRECISE = dataset_pb2.PII_CATEGORY_GEOLOCATION_PRECISE
	GEOLOCATION_COARSE = dataset_pb2.PII_CATEGORY_GEOLOCATION_COARSE
	BIRTH_DATE = dataset_pb2.PII_CATEGORY_BIRTH_DATE
	GENDER = dataset_pb2.PII_CATEGORY_GENDER
	HEALTH_DATA = dataset_pb2.PII_CATEGORY_HEALTH_DATA
	BIOMETRIC_DATA = dataset_pb2.PII_CATEGORY_BIOMETRIC_DATA
	FINANCIAL_DATA = dataset_pb2.PII_CATEGORY_FINANCIAL_DATA
	POLITICAL_RELIGIOUS = dataset_pb2.PII_CATEGORY_POLITICAL_RELIGIOUS


class DataSubjectType(IntEnum):
	UNSPECIFIED = dataset_pb2.DATA_SUBJECT_TYPE_UNSPECIFIED
	CUSTOMER = dataset_pb2.DATA_SUBJECT_TYPE_CUSTOMER
	EMPLOYEE = dataset_pb2.DATA_SUBJECT_TYPE_EMPLOYEE
	PATIENT = dataset_pb2.DATA_SUBJECT_TYPE_PATIENT
	STUDENT = dataset_pb2.DATA_SUBJECT_TYPE_STUDENT
	MINOR = dataset_pb2.DATA_SUBJECT_TYPE_MINOR
	PUBLIC_FIGURE = dataset_pb2.DATA_SUBJECT_TYPE_PUBLIC_FIGURE


# ==============================================================================
# Sub-Models
# ==============================================================================


class LicenseInfo(AmbyteBaseModel):
	spdx_id: str = ''
	name: str = ''
	url: str = ''
	commercial_use_allowed: bool = False
	modification_allowed: bool = False
	redistribution_allowed: bool = False
	ai_training_allowed: bool = False

	def to_proto(self) -> dataset_pb2.LicenseInfo:
		return dataset_pb2.LicenseInfo(
			spdx_id=self.spdx_id,
			name=self.name,
			url=self.url,
			commercial_use_allowed=self.commercial_use_allowed,
			modification_allowed=self.modification_allowed,
			redistribution_allowed=self.redistribution_allowed,
			ai_training_allowed=self.ai_training_allowed,
		)

	@classmethod
	def from_proto(cls, proto: dataset_pb2.LicenseInfo) -> 'LicenseInfo':
		return cls(
			spdx_id=proto.spdx_id,
			name=proto.name,
			url=proto.url,
			commercial_use_allowed=proto.commercial_use_allowed,
			modification_allowed=proto.modification_allowed,
			redistribution_allowed=proto.redistribution_allowed,
			ai_training_allowed=proto.ai_training_allowed,
		)


class SchemaField(AmbyteBaseModel):
	name: str
	native_type: str
	is_pii: bool = False
	pii_category: PiiCategory = PiiCategory.NONE
	sensitivity: SensitivityLevel = SensitivityLevel.UNSPECIFIED
	is_identifier: bool = False

	def to_proto(self) -> dataset_pb2.SchemaField:
		return dataset_pb2.SchemaField(
			name=self.name,
			native_type=self.native_type,
			is_pii=self.is_pii,
			pii_category=self.pii_category.value,
			sensitivity=self.sensitivity.value,
			is_identifier=self.is_identifier,
		)

	@classmethod
	def from_proto(cls, proto: dataset_pb2.SchemaField) -> 'SchemaField':
		return cls(
			name=proto.name,
			native_type=proto.native_type,
			is_pii=proto.is_pii,
			pii_category=PiiCategory(proto.pii_category),
			sensitivity=SensitivityLevel(proto.sensitivity),
			is_identifier=proto.is_identifier,
		)


# ==============================================================================
# Main Model
# ==============================================================================


class Dataset(AmbyteBaseModel):
	id: str
	urn: str
	name: str
	description: str = ''
	owner: Actor | None = None
	resource: ResourceIdentifier | None = None
	fields: list[SchemaField] = Field(default_factory=list)
	sensitivity: SensitivityLevel = SensitivityLevel.UNSPECIFIED
	geo_region: str = ''  # ISO Code
	data_subjects: list[DataSubjectType] = Field(default_factory=list)
	license: LicenseInfo | None = None

	created_at: datetime | None = None
	updated_at: datetime | None = None

	def to_proto(self) -> dataset_pb2.Dataset:
		# Handle Timestamps
		created_ts = Timestamp()
		if self.created_at:
			created_ts.FromDatetime(self.created_at)

		updated_ts = Timestamp()
		if self.updated_at:
			updated_ts.FromDatetime(self.updated_at)

		return dataset_pb2.Dataset(
			id=self.id,
			urn=self.urn,
			name=self.name,
			description=self.description,
			owner=self.owner.to_proto() if self.owner else None,
			resource=self.resource.to_proto() if self.resource else None,
			fields=[f.to_proto() for f in self.fields],
			sensitivity=self.sensitivity.value,
			geo_region=self.geo_region,
			data_subjects=[ds.value for ds in self.data_subjects],
			license=self.license.to_proto() if self.license else None,
			created_at=created_ts if self.created_at else None,
			updated_at=updated_ts if self.updated_at else None,
		)

	@classmethod
	def from_proto(cls, proto: dataset_pb2.Dataset) -> 'Dataset':
		return cls(
			id=proto.id,
			urn=proto.urn,
			name=proto.name,
			description=proto.description,
			owner=Actor.from_proto(proto.owner) if proto.HasField('owner') else None,
			resource=ResourceIdentifier.from_proto(proto.resource) if proto.HasField('resource') else None,
			fields=[SchemaField.from_proto(f) for f in proto.fields],
			sensitivity=SensitivityLevel(proto.sensitivity),
			geo_region=proto.geo_region,
			data_subjects=[DataSubjectType(ds) for ds in proto.data_subjects],
			license=LicenseInfo.from_proto(proto.license) if proto.HasField('license') else None,
			# Convert Protobuf Timestamp to Python datetime
			created_at=proto.created_at.ToDatetime() if proto.HasField('created_at') else None,
			updated_at=proto.updated_at.ToDatetime() if proto.HasField('updated_at') else None,
		)

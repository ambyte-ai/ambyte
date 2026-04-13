import datetime

from common.v1 import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PiiCategory(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PII_CATEGORY_UNSPECIFIED: _ClassVar[PiiCategory]
    PII_CATEGORY_NONE: _ClassVar[PiiCategory]
    PII_CATEGORY_EMAIL_ADDRESS: _ClassVar[PiiCategory]
    PII_CATEGORY_PHONE_NUMBER: _ClassVar[PiiCategory]
    PII_CATEGORY_FULL_NAME: _ClassVar[PiiCategory]
    PII_CATEGORY_GOV_ID: _ClassVar[PiiCategory]
    PII_CATEGORY_IP_ADDRESS: _ClassVar[PiiCategory]
    PII_CATEGORY_DEVICE_ID: _ClassVar[PiiCategory]
    PII_CATEGORY_GEOLOCATION_PRECISE: _ClassVar[PiiCategory]
    PII_CATEGORY_GEOLOCATION_COARSE: _ClassVar[PiiCategory]
    PII_CATEGORY_BIRTH_DATE: _ClassVar[PiiCategory]
    PII_CATEGORY_GENDER: _ClassVar[PiiCategory]
    PII_CATEGORY_HEALTH_DATA: _ClassVar[PiiCategory]
    PII_CATEGORY_BIOMETRIC_DATA: _ClassVar[PiiCategory]
    PII_CATEGORY_FINANCIAL_DATA: _ClassVar[PiiCategory]
    PII_CATEGORY_POLITICAL_RELIGIOUS: _ClassVar[PiiCategory]

class DataSubjectType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DATA_SUBJECT_TYPE_UNSPECIFIED: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_CUSTOMER: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_EMPLOYEE: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_PATIENT: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_STUDENT: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_MINOR: _ClassVar[DataSubjectType]
    DATA_SUBJECT_TYPE_PUBLIC_FIGURE: _ClassVar[DataSubjectType]
PII_CATEGORY_UNSPECIFIED: PiiCategory
PII_CATEGORY_NONE: PiiCategory
PII_CATEGORY_EMAIL_ADDRESS: PiiCategory
PII_CATEGORY_PHONE_NUMBER: PiiCategory
PII_CATEGORY_FULL_NAME: PiiCategory
PII_CATEGORY_GOV_ID: PiiCategory
PII_CATEGORY_IP_ADDRESS: PiiCategory
PII_CATEGORY_DEVICE_ID: PiiCategory
PII_CATEGORY_GEOLOCATION_PRECISE: PiiCategory
PII_CATEGORY_GEOLOCATION_COARSE: PiiCategory
PII_CATEGORY_BIRTH_DATE: PiiCategory
PII_CATEGORY_GENDER: PiiCategory
PII_CATEGORY_HEALTH_DATA: PiiCategory
PII_CATEGORY_BIOMETRIC_DATA: PiiCategory
PII_CATEGORY_FINANCIAL_DATA: PiiCategory
PII_CATEGORY_POLITICAL_RELIGIOUS: PiiCategory
DATA_SUBJECT_TYPE_UNSPECIFIED: DataSubjectType
DATA_SUBJECT_TYPE_CUSTOMER: DataSubjectType
DATA_SUBJECT_TYPE_EMPLOYEE: DataSubjectType
DATA_SUBJECT_TYPE_PATIENT: DataSubjectType
DATA_SUBJECT_TYPE_STUDENT: DataSubjectType
DATA_SUBJECT_TYPE_MINOR: DataSubjectType
DATA_SUBJECT_TYPE_PUBLIC_FIGURE: DataSubjectType

class Dataset(_message.Message):
    __slots__ = ("id", "urn", "name", "description", "owner", "resource", "fields", "sensitivity", "geo_region", "data_subjects", "license", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    URN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    SENSITIVITY_FIELD_NUMBER: _ClassVar[int]
    GEO_REGION_FIELD_NUMBER: _ClassVar[int]
    DATA_SUBJECTS_FIELD_NUMBER: _ClassVar[int]
    LICENSE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    urn: str
    name: str
    description: str
    owner: _common_pb2.Actor
    resource: _common_pb2.ResourceIdentifier
    fields: _containers.RepeatedCompositeFieldContainer[SchemaField]
    sensitivity: _common_pb2.SensitivityLevel
    geo_region: str
    data_subjects: _containers.RepeatedScalarFieldContainer[DataSubjectType]
    license: LicenseInfo
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., urn: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., owner: _Optional[_Union[_common_pb2.Actor, _Mapping]] = ..., resource: _Optional[_Union[_common_pb2.ResourceIdentifier, _Mapping]] = ..., fields: _Optional[_Iterable[_Union[SchemaField, _Mapping]]] = ..., sensitivity: _Optional[_Union[_common_pb2.SensitivityLevel, str]] = ..., geo_region: _Optional[str] = ..., data_subjects: _Optional[_Iterable[_Union[DataSubjectType, str]]] = ..., license: _Optional[_Union[LicenseInfo, _Mapping]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SchemaField(_message.Message):
    __slots__ = ("name", "native_type", "is_pii", "pii_category", "sensitivity", "is_identifier")
    NAME_FIELD_NUMBER: _ClassVar[int]
    NATIVE_TYPE_FIELD_NUMBER: _ClassVar[int]
    IS_PII_FIELD_NUMBER: _ClassVar[int]
    PII_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    SENSITIVITY_FIELD_NUMBER: _ClassVar[int]
    IS_IDENTIFIER_FIELD_NUMBER: _ClassVar[int]
    name: str
    native_type: str
    is_pii: bool
    pii_category: PiiCategory
    sensitivity: _common_pb2.SensitivityLevel
    is_identifier: bool
    def __init__(self, name: _Optional[str] = ..., native_type: _Optional[str] = ..., is_pii: _Optional[bool] = ..., pii_category: _Optional[_Union[PiiCategory, str]] = ..., sensitivity: _Optional[_Union[_common_pb2.SensitivityLevel, str]] = ..., is_identifier: _Optional[bool] = ...) -> None: ...

class LicenseInfo(_message.Message):
    __slots__ = ("spdx_id", "name", "url", "commercial_use_allowed", "modification_allowed", "redistribution_allowed", "ai_training_allowed")
    SPDX_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    COMMERCIAL_USE_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    MODIFICATION_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    REDISTRIBUTION_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    AI_TRAINING_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    spdx_id: str
    name: str
    url: str
    commercial_use_allowed: bool
    modification_allowed: bool
    redistribution_allowed: bool
    ai_training_allowed: bool
    def __init__(self, spdx_id: _Optional[str] = ..., name: _Optional[str] = ..., url: _Optional[str] = ..., commercial_use_allowed: _Optional[bool] = ..., modification_allowed: _Optional[bool] = ..., redistribution_allowed: _Optional[bool] = ..., ai_training_allowed: _Optional[bool] = ...) -> None: ...

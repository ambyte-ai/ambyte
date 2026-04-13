import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EnforcementLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ENFORCEMENT_LEVEL_UNSPECIFIED: _ClassVar[EnforcementLevel]
    ENFORCEMENT_LEVEL_BLOCKING: _ClassVar[EnforcementLevel]
    ENFORCEMENT_LEVEL_AUDIT_ONLY: _ClassVar[EnforcementLevel]
    ENFORCEMENT_LEVEL_NOTIFY_HUMAN: _ClassVar[EnforcementLevel]
ENFORCEMENT_LEVEL_UNSPECIFIED: EnforcementLevel
ENFORCEMENT_LEVEL_BLOCKING: EnforcementLevel
ENFORCEMENT_LEVEL_AUDIT_ONLY: EnforcementLevel
ENFORCEMENT_LEVEL_NOTIFY_HUMAN: EnforcementLevel

class Obligation(_message.Message):
    __slots__ = ("id", "title", "description", "provenance", "enforcement_level", "target", "is_active", "retention", "geofencing", "purpose", "privacy", "ai_model", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PROVENANCE_FIELD_NUMBER: _ClassVar[int]
    ENFORCEMENT_LEVEL_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    RETENTION_FIELD_NUMBER: _ClassVar[int]
    GEOFENCING_FIELD_NUMBER: _ClassVar[int]
    PURPOSE_FIELD_NUMBER: _ClassVar[int]
    PRIVACY_FIELD_NUMBER: _ClassVar[int]
    AI_MODEL_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    description: str
    provenance: SourceProvenance
    enforcement_level: EnforcementLevel
    target: ResourceSelector
    is_active: bool
    retention: RetentionRule
    geofencing: GeofencingRule
    purpose: PurposeRestriction
    privacy: PrivacyEnhancementRule
    ai_model: AiModelConstraint
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., provenance: _Optional[_Union[SourceProvenance, _Mapping]] = ..., enforcement_level: _Optional[_Union[EnforcementLevel, str]] = ..., target: _Optional[_Union[ResourceSelector, _Mapping]] = ..., is_active: _Optional[bool] = ..., retention: _Optional[_Union[RetentionRule, _Mapping]] = ..., geofencing: _Optional[_Union[GeofencingRule, _Mapping]] = ..., purpose: _Optional[_Union[PurposeRestriction, _Mapping]] = ..., privacy: _Optional[_Union[PrivacyEnhancementRule, _Mapping]] = ..., ai_model: _Optional[_Union[AiModelConstraint, _Mapping]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ResourceSelector(_message.Message):
    __slots__ = ("include_patterns", "exclude_patterns", "match_tags")
    class MatchTagsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INCLUDE_PATTERNS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDE_PATTERNS_FIELD_NUMBER: _ClassVar[int]
    MATCH_TAGS_FIELD_NUMBER: _ClassVar[int]
    include_patterns: _containers.RepeatedScalarFieldContainer[str]
    exclude_patterns: _containers.RepeatedScalarFieldContainer[str]
    match_tags: _containers.ScalarMap[str, str]
    def __init__(self, include_patterns: _Optional[_Iterable[str]] = ..., exclude_patterns: _Optional[_Iterable[str]] = ..., match_tags: _Optional[_Mapping[str, str]] = ...) -> None: ...

class RetentionRule(_message.Message):
    __slots__ = ("duration", "trigger", "allow_legal_hold_override")
    class RetentionTrigger(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        RETENTION_TRIGGER_UNSPECIFIED: _ClassVar[RetentionRule.RetentionTrigger]
        RETENTION_TRIGGER_CREATION_DATE: _ClassVar[RetentionRule.RetentionTrigger]
        RETENTION_TRIGGER_LAST_ACCESS_DATE: _ClassVar[RetentionRule.RetentionTrigger]
        RETENTION_TRIGGER_EVENT_DATE: _ClassVar[RetentionRule.RetentionTrigger]
        RETENTION_TRIGGER_DATA_SUBJECT_REQUEST: _ClassVar[RetentionRule.RetentionTrigger]
    RETENTION_TRIGGER_UNSPECIFIED: RetentionRule.RetentionTrigger
    RETENTION_TRIGGER_CREATION_DATE: RetentionRule.RetentionTrigger
    RETENTION_TRIGGER_LAST_ACCESS_DATE: RetentionRule.RetentionTrigger
    RETENTION_TRIGGER_EVENT_DATE: RetentionRule.RetentionTrigger
    RETENTION_TRIGGER_DATA_SUBJECT_REQUEST: RetentionRule.RetentionTrigger
    DURATION_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_FIELD_NUMBER: _ClassVar[int]
    ALLOW_LEGAL_HOLD_OVERRIDE_FIELD_NUMBER: _ClassVar[int]
    duration: _duration_pb2.Duration
    trigger: RetentionRule.RetentionTrigger
    allow_legal_hold_override: bool
    def __init__(self, duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., trigger: _Optional[_Union[RetentionRule.RetentionTrigger, str]] = ..., allow_legal_hold_override: _Optional[bool] = ...) -> None: ...

class GeofencingRule(_message.Message):
    __slots__ = ("allowed_regions", "denied_regions", "strict_residency")
    ALLOWED_REGIONS_FIELD_NUMBER: _ClassVar[int]
    DENIED_REGIONS_FIELD_NUMBER: _ClassVar[int]
    STRICT_RESIDENCY_FIELD_NUMBER: _ClassVar[int]
    allowed_regions: _containers.RepeatedScalarFieldContainer[str]
    denied_regions: _containers.RepeatedScalarFieldContainer[str]
    strict_residency: bool
    def __init__(self, allowed_regions: _Optional[_Iterable[str]] = ..., denied_regions: _Optional[_Iterable[str]] = ..., strict_residency: _Optional[bool] = ...) -> None: ...

class PurposeRestriction(_message.Message):
    __slots__ = ("allowed_purposes", "denied_purposes")
    ALLOWED_PURPOSES_FIELD_NUMBER: _ClassVar[int]
    DENIED_PURPOSES_FIELD_NUMBER: _ClassVar[int]
    allowed_purposes: _containers.RepeatedScalarFieldContainer[str]
    denied_purposes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, allowed_purposes: _Optional[_Iterable[str]] = ..., denied_purposes: _Optional[_Iterable[str]] = ...) -> None: ...

class PrivacyEnhancementRule(_message.Message):
    __slots__ = ("method", "parameters")
    class PrivacyMethod(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        PRIVACY_METHOD_UNSPECIFIED: _ClassVar[PrivacyEnhancementRule.PrivacyMethod]
        PRIVACY_METHOD_PSEUDONYMIZATION: _ClassVar[PrivacyEnhancementRule.PrivacyMethod]
        PRIVACY_METHOD_ANONYMIZATION: _ClassVar[PrivacyEnhancementRule.PrivacyMethod]
        PRIVACY_METHOD_DIFFERENTIAL_PRIVACY: _ClassVar[PrivacyEnhancementRule.PrivacyMethod]
        PRIVACY_METHOD_ROW_LEVEL_SECURITY: _ClassVar[PrivacyEnhancementRule.PrivacyMethod]
    PRIVACY_METHOD_UNSPECIFIED: PrivacyEnhancementRule.PrivacyMethod
    PRIVACY_METHOD_PSEUDONYMIZATION: PrivacyEnhancementRule.PrivacyMethod
    PRIVACY_METHOD_ANONYMIZATION: PrivacyEnhancementRule.PrivacyMethod
    PRIVACY_METHOD_DIFFERENTIAL_PRIVACY: PrivacyEnhancementRule.PrivacyMethod
    PRIVACY_METHOD_ROW_LEVEL_SECURITY: PrivacyEnhancementRule.PrivacyMethod
    class ParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    METHOD_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    method: PrivacyEnhancementRule.PrivacyMethod
    parameters: _containers.ScalarMap[str, str]
    def __init__(self, method: _Optional[_Union[PrivacyEnhancementRule.PrivacyMethod, str]] = ..., parameters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AiModelConstraint(_message.Message):
    __slots__ = ("training_allowed", "fine_tuning_allowed", "rag_usage_allowed", "requires_open_source_release", "attribution_text_required")
    TRAINING_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    FINE_TUNING_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    RAG_USAGE_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_OPEN_SOURCE_RELEASE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTION_TEXT_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    training_allowed: bool
    fine_tuning_allowed: bool
    rag_usage_allowed: bool
    requires_open_source_release: bool
    attribution_text_required: str
    def __init__(self, training_allowed: _Optional[bool] = ..., fine_tuning_allowed: _Optional[bool] = ..., rag_usage_allowed: _Optional[bool] = ..., requires_open_source_release: _Optional[bool] = ..., attribution_text_required: _Optional[str] = ...) -> None: ...

class SourceProvenance(_message.Message):
    __slots__ = ("source_id", "document_type", "section_reference", "document_uri")
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    DOCUMENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SECTION_REFERENCE_FIELD_NUMBER: _ClassVar[int]
    DOCUMENT_URI_FIELD_NUMBER: _ClassVar[int]
    source_id: str
    document_type: str
    section_reference: str
    document_uri: str
    def __init__(self, source_id: _Optional[str] = ..., document_type: _Optional[str] = ..., section_reference: _Optional[str] = ..., document_uri: _Optional[str] = ...) -> None: ...

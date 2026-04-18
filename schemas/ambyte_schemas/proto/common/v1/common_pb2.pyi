from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar
from typing import Optional as _Optional
from typing import Union as _Union

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class SensitivityLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SENSITIVITY_LEVEL_UNSPECIFIED: _ClassVar[SensitivityLevel]
    SENSITIVITY_LEVEL_PUBLIC: _ClassVar[SensitivityLevel]
    SENSITIVITY_LEVEL_INTERNAL: _ClassVar[SensitivityLevel]
    SENSITIVITY_LEVEL_CONFIDENTIAL: _ClassVar[SensitivityLevel]
    SENSITIVITY_LEVEL_RESTRICTED: _ClassVar[SensitivityLevel]

class RiskSeverity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RISK_SEVERITY_UNSPECIFIED: _ClassVar[RiskSeverity]
    RISK_SEVERITY_LOW: _ClassVar[RiskSeverity]
    RISK_SEVERITY_MEDIUM: _ClassVar[RiskSeverity]
    RISK_SEVERITY_HIGH: _ClassVar[RiskSeverity]
    RISK_SEVERITY_UNACCEPTABLE: _ClassVar[RiskSeverity]
SENSITIVITY_LEVEL_UNSPECIFIED: SensitivityLevel
SENSITIVITY_LEVEL_PUBLIC: SensitivityLevel
SENSITIVITY_LEVEL_INTERNAL: SensitivityLevel
SENSITIVITY_LEVEL_CONFIDENTIAL: SensitivityLevel
SENSITIVITY_LEVEL_RESTRICTED: SensitivityLevel
RISK_SEVERITY_UNSPECIFIED: RiskSeverity
RISK_SEVERITY_LOW: RiskSeverity
RISK_SEVERITY_MEDIUM: RiskSeverity
RISK_SEVERITY_HIGH: RiskSeverity
RISK_SEVERITY_UNACCEPTABLE: RiskSeverity

class Actor(_message.Message):
    __slots__ = ("id", "type", "roles", "attributes")
    class ActorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ACTOR_TYPE_UNSPECIFIED: _ClassVar[Actor.ActorType]
        ACTOR_TYPE_HUMAN: _ClassVar[Actor.ActorType]
        ACTOR_TYPE_SERVICE_ACCOUNT: _ClassVar[Actor.ActorType]
        ACTOR_TYPE_SYSTEM_INTERNAL: _ClassVar[Actor.ActorType]
    ACTOR_TYPE_UNSPECIFIED: Actor.ActorType
    ACTOR_TYPE_HUMAN: Actor.ActorType
    ACTOR_TYPE_SERVICE_ACCOUNT: Actor.ActorType
    ACTOR_TYPE_SYSTEM_INTERNAL: Actor.ActorType
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: Actor.ActorType
    roles: _containers.RepeatedScalarFieldContainer[str]
    attributes: _containers.ScalarMap[str, str]
    def __init__(self, id: _Optional[str] = ..., type: _Optional[_Union[Actor.ActorType, str]] = ..., roles: _Optional[_Iterable[str]] = ..., attributes: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ResourceIdentifier(_message.Message):
    __slots__ = ("platform", "location", "native_id")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    NATIVE_ID_FIELD_NUMBER: _ClassVar[int]
    platform: str
    location: str
    native_id: str
    def __init__(self, platform: _Optional[str] = ..., location: _Optional[str] = ..., native_id: _Optional[str] = ...) -> None: ...

class Tag(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

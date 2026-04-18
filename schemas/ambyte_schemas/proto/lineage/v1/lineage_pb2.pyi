import datetime
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar
from typing import Optional as _Optional
from typing import Union as _Union

from common.v1 import common_pb2 as _common_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class Run(_message.Message):
    __slots__ = ("id", "type", "triggered_by", "start_time", "end_time", "success")
    class RunType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        RUN_TYPE_UNSPECIFIED: _ClassVar[Run.RunType]
        RUN_TYPE_ETL_TRANSFORM: _ClassVar[Run.RunType]
        RUN_TYPE_AI_TRAINING: _ClassVar[Run.RunType]
        RUN_TYPE_AI_FINE_TUNING: _ClassVar[Run.RunType]
        RUN_TYPE_AI_RAG_QUERY: _ClassVar[Run.RunType]
        RUN_TYPE_HUMAN_DOWNLOAD: _ClassVar[Run.RunType]
    RUN_TYPE_UNSPECIFIED: Run.RunType
    RUN_TYPE_ETL_TRANSFORM: Run.RunType
    RUN_TYPE_AI_TRAINING: Run.RunType
    RUN_TYPE_AI_FINE_TUNING: Run.RunType
    RUN_TYPE_AI_RAG_QUERY: Run.RunType
    RUN_TYPE_HUMAN_DOWNLOAD: Run.RunType
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TRIGGERED_BY_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: Run.RunType
    triggered_by: _common_pb2.Actor
    start_time: _timestamp_pb2.Timestamp
    end_time: _timestamp_pb2.Timestamp
    success: bool
    def __init__(self, id: _Optional[str] = ..., type: _Optional[_Union[Run.RunType, str]] = ..., triggered_by: _Optional[_Union[_common_pb2.Actor, _Mapping]] = ..., start_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., success: _Optional[bool] = ...) -> None: ...

class LineageEvent(_message.Message):
    __slots__ = ("run_id", "input_urns", "output_urns")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    INPUT_URNS_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_URNS_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    input_urns: _containers.RepeatedScalarFieldContainer[str]
    output_urns: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, run_id: _Optional[str] = ..., input_urns: _Optional[_Iterable[str]] = ..., output_urns: _Optional[_Iterable[str]] = ...) -> None: ...

class ModelArtifact(_message.Message):
    __slots__ = ("id", "urn", "name", "version", "model_type", "risk_level", "base_model_urn")
    class ModelType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        MODEL_TYPE_UNSPECIFIED: _ClassVar[ModelArtifact.ModelType]
        MODEL_TYPE_LLM: _ClassVar[ModelArtifact.ModelType]
        MODEL_TYPE_COMPUTER_VISION: _ClassVar[ModelArtifact.ModelType]
        MODEL_TYPE_TABULAR_REGRESSOR: _ClassVar[ModelArtifact.ModelType]
        MODEL_TYPE_EMBEDDING: _ClassVar[ModelArtifact.ModelType]
    MODEL_TYPE_UNSPECIFIED: ModelArtifact.ModelType
    MODEL_TYPE_LLM: ModelArtifact.ModelType
    MODEL_TYPE_COMPUTER_VISION: ModelArtifact.ModelType
    MODEL_TYPE_TABULAR_REGRESSOR: ModelArtifact.ModelType
    MODEL_TYPE_EMBEDDING: ModelArtifact.ModelType
    ID_FIELD_NUMBER: _ClassVar[int]
    URN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_TYPE_FIELD_NUMBER: _ClassVar[int]
    RISK_LEVEL_FIELD_NUMBER: _ClassVar[int]
    BASE_MODEL_URN_FIELD_NUMBER: _ClassVar[int]
    id: str
    urn: str
    name: str
    version: str
    model_type: ModelArtifact.ModelType
    risk_level: _common_pb2.RiskSeverity
    base_model_urn: str
    def __init__(self, id: _Optional[str] = ..., urn: _Optional[str] = ..., name: _Optional[str] = ..., version: _Optional[str] = ..., model_type: _Optional[_Union[ModelArtifact.ModelType, str]] = ..., risk_level: _Optional[_Union[_common_pb2.RiskSeverity, str]] = ..., base_model_urn: _Optional[str] = ...) -> None: ...

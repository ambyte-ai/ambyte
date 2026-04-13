import datetime

from common.v1 import common_pb2 as _common_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Decision(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DECISION_UNSPECIFIED: _ClassVar[Decision]
    DECISION_ALLOW: _ClassVar[Decision]
    DECISION_DENY: _ClassVar[Decision]
    DECISION_DRY_RUN_DENY: _ClassVar[Decision]
DECISION_UNSPECIFIED: Decision
DECISION_ALLOW: Decision
DECISION_DENY: Decision
DECISION_DRY_RUN_DENY: Decision

class AuditLogEntry(_message.Message):
    __slots__ = ("id", "timestamp", "actor", "resource_urn", "action", "decision", "evaluation_trace", "request_context", "entry_hash")
    ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_URN_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    EVALUATION_TRACE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ENTRY_HASH_FIELD_NUMBER: _ClassVar[int]
    id: str
    timestamp: _timestamp_pb2.Timestamp
    actor: _common_pb2.Actor
    resource_urn: str
    action: str
    decision: Decision
    evaluation_trace: PolicyEvaluationTrace
    request_context: _struct_pb2.Struct
    entry_hash: str
    def __init__(self, id: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., actor: _Optional[_Union[_common_pb2.Actor, _Mapping]] = ..., resource_urn: _Optional[str] = ..., action: _Optional[str] = ..., decision: _Optional[_Union[Decision, str]] = ..., evaluation_trace: _Optional[_Union[PolicyEvaluationTrace, _Mapping]] = ..., request_context: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., entry_hash: _Optional[str] = ...) -> None: ...

class PolicyEvaluationTrace(_message.Message):
    __slots__ = ("reason_summary", "contributing_obligation_ids", "policy_version_hash", "cache_hit")
    REASON_SUMMARY_FIELD_NUMBER: _ClassVar[int]
    CONTRIBUTING_OBLIGATION_IDS_FIELD_NUMBER: _ClassVar[int]
    POLICY_VERSION_HASH_FIELD_NUMBER: _ClassVar[int]
    CACHE_HIT_FIELD_NUMBER: _ClassVar[int]
    reason_summary: str
    contributing_obligation_ids: _containers.RepeatedScalarFieldContainer[str]
    policy_version_hash: str
    cache_hit: bool
    def __init__(self, reason_summary: _Optional[str] = ..., contributing_obligation_ids: _Optional[_Iterable[str]] = ..., policy_version_hash: _Optional[str] = ..., cache_hit: _Optional[bool] = ...) -> None: ...

class AuditBlockHeader(_message.Message):
    __slots__ = ("id", "sequence_index", "prev_block_hash", "merkle_root", "timestamp_start", "timestamp_end", "log_count", "signature")
    ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_INDEX_FIELD_NUMBER: _ClassVar[int]
    PREV_BLOCK_HASH_FIELD_NUMBER: _ClassVar[int]
    MERKLE_ROOT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_START_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_END_FIELD_NUMBER: _ClassVar[int]
    LOG_COUNT_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    id: str
    sequence_index: int
    prev_block_hash: str
    merkle_root: str
    timestamp_start: _timestamp_pb2.Timestamp
    timestamp_end: _timestamp_pb2.Timestamp
    log_count: int
    signature: bytes
    def __init__(self, id: _Optional[str] = ..., sequence_index: _Optional[int] = ..., prev_block_hash: _Optional[str] = ..., merkle_root: _Optional[str] = ..., timestamp_start: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., timestamp_end: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., log_count: _Optional[int] = ..., signature: _Optional[bytes] = ...) -> None: ...

class AuditProof(_message.Message):
    __slots__ = ("entry", "block_header", "merkle_siblings")
    ENTRY_FIELD_NUMBER: _ClassVar[int]
    BLOCK_HEADER_FIELD_NUMBER: _ClassVar[int]
    MERKLE_SIBLINGS_FIELD_NUMBER: _ClassVar[int]
    entry: AuditLogEntry
    block_header: AuditBlockHeader
    merkle_siblings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, entry: _Optional[_Union[AuditLogEntry, _Mapping]] = ..., block_header: _Optional[_Union[AuditBlockHeader, _Mapping]] = ..., merkle_siblings: _Optional[_Iterable[str]] = ...) -> None: ...

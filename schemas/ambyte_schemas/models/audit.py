from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, cast

from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import Field

from ambyte_schemas.models.common import Actor, AmbyteBaseModel
from ambyte_schemas.proto.audit.v1 import audit_pb2

# ==============================================================================
# Enums
# ==============================================================================


class Decision(IntEnum):
	UNSPECIFIED = audit_pb2.DECISION_UNSPECIFIED
	ALLOW = audit_pb2.DECISION_ALLOW
	DENY = audit_pb2.DECISION_DENY
	DRY_RUN_DENY = audit_pb2.DECISION_DRY_RUN_DENY


# ==============================================================================
# Sub-Models
# ==============================================================================


class PolicyEvaluationTrace(AmbyteBaseModel):
	reason_summary: str
	contributing_obligation_ids: list[str] = Field(default_factory=list)
	policy_version_hash: str = ''
	cache_hit: bool = False

	def to_proto(self) -> audit_pb2.PolicyEvaluationTrace:
		return audit_pb2.PolicyEvaluationTrace(
			reason_summary=self.reason_summary,
			contributing_obligation_ids=self.contributing_obligation_ids,
			policy_version_hash=self.policy_version_hash,
			cache_hit=self.cache_hit,
		)

	@classmethod
	def from_proto(cls, proto: audit_pb2.PolicyEvaluationTrace) -> 'PolicyEvaluationTrace':
		return cls(
			reason_summary=proto.reason_summary,
			contributing_obligation_ids=list(proto.contributing_obligation_ids),
			policy_version_hash=proto.policy_version_hash,
			cache_hit=proto.cache_hit,
		)


# ==============================================================================
# Core Log Entry
# ==============================================================================


class AuditLogEntry(AmbyteBaseModel):
	id: str
	timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	actor: Actor
	resource_urn: str
	action: str
	decision: Decision
	evaluation_trace: PolicyEvaluationTrace | None = None
	request_context: dict[str, Any] = Field(default_factory=dict)
	entry_hash: str = ''

	def to_proto(self) -> audit_pb2.AuditLogEntry:
		# Handle Timestamp
		ts = Timestamp()
		if self.timestamp:
			ts.FromDatetime(self.timestamp)

		# Handle Struct (Context)
		ctx_struct = Struct()
		if self.request_context:
			# Struct.update expects a dict
			ctx_struct.update(self.request_context)

		return audit_pb2.AuditLogEntry(
			id=self.id,
			timestamp=ts,
			actor=self.actor.to_proto(),
			resource_urn=self.resource_urn,
			action=self.action,
			decision=cast(Any, self.decision),
			evaluation_trace=self.evaluation_trace.to_proto() if self.evaluation_trace else None,
			request_context=ctx_struct,
			entry_hash=self.entry_hash,
		)

	@classmethod
	def from_proto(cls, proto: audit_pb2.AuditLogEntry) -> 'AuditLogEntry':
		# Convert Struct -> Dict
		ctx_dict = dict(proto.request_context.items())

		return cls(
			id=proto.id,
			timestamp=proto.timestamp.ToDatetime().replace(tzinfo=timezone.utc),
			actor=Actor.from_proto(proto.actor),
			resource_urn=proto.resource_urn,
			action=proto.action,
			decision=Decision(proto.decision),
			evaluation_trace=(
				PolicyEvaluationTrace.from_proto(proto.evaluation_trace) if proto.HasField('evaluation_trace') else None
			),
			request_context=ctx_dict,
			entry_hash=proto.entry_hash,
		)


# ==============================================================================
# Cryptographic Proof Models
# ==============================================================================


class AuditBlockHeader(AmbyteBaseModel):
	id: str
	sequence_index: int
	prev_block_hash: str
	merkle_root: str
	timestamp_start: datetime
	timestamp_end: datetime
	log_count: int
	signature: bytes

	def to_proto(self) -> audit_pb2.AuditBlockHeader:
		start = Timestamp()
		start.FromDatetime(self.timestamp_start)
		end = Timestamp()
		end.FromDatetime(self.timestamp_end)

		return audit_pb2.AuditBlockHeader(
			id=self.id,
			sequence_index=self.sequence_index,
			prev_block_hash=self.prev_block_hash,
			merkle_root=self.merkle_root,
			timestamp_start=start,
			timestamp_end=end,
			log_count=self.log_count,
			signature=self.signature,
		)

	@classmethod
	def from_proto(cls, proto: audit_pb2.AuditBlockHeader) -> 'AuditBlockHeader':
		return cls(
			id=proto.id,
			sequence_index=proto.sequence_index,
			prev_block_hash=proto.prev_block_hash,
			merkle_root=proto.merkle_root,
			timestamp_start=proto.timestamp_start.ToDatetime().replace(tzinfo=timezone.utc),
			timestamp_end=proto.timestamp_end.ToDatetime().replace(tzinfo=timezone.utc),
			log_count=proto.log_count,
			signature=proto.signature,
		)


class AuditProof(AmbyteBaseModel):
	entry: AuditLogEntry
	block_header: AuditBlockHeader
	merkle_siblings: list[str]

	def to_proto(self) -> audit_pb2.AuditProof:
		return audit_pb2.AuditProof(
			entry=self.entry.to_proto(),
			block_header=self.block_header.to_proto(),
			merkle_siblings=self.merkle_siblings,
		)

	@classmethod
	def from_proto(cls, proto: audit_pb2.AuditProof) -> 'AuditProof':
		return cls(
			entry=AuditLogEntry.from_proto(proto.entry),
			block_header=AuditBlockHeader.from_proto(proto.block_header),
			merkle_siblings=list(proto.merkle_siblings),
		)

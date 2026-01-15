from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, ProjectScopedMixin):
	"""
	Immutable ledger of all policy checks and enforcement actions.
	This table handles HIGH WRITE volume.
	TODO: In a high-scale production setup (Postgres 13+),
	we would convert this to a native partitioned table (partition by range on timestamp).
	"""

	__tablename__ = 'audit_logs'

	# When did the check happen? (Indexed for range queries)
	timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)

	# WHO: The Actor ID (e.g., "user_123" or "airflow-worker")
	actor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

	# WHAT: The Resource URN
	resource_urn: Mapped[str] = mapped_column(String, nullable=False, index=True)

	# HOW: The Action attempted (e.g., "read", "training_run")
	action: Mapped[str] = mapped_column(String, nullable=False)

	# RESULT: "ALLOW" or "DENY"
	decision: Mapped[str] = mapped_column(String, nullable=False)

	# WHY: The trace of which policies contributed to the decision.
	# e.g. { "blocking_policy_id": "gdpr-art-17", "reason": "Retention expired" }
	reason_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=True)

	# CONTEXT: Snapshot of the request context (region, purpose) for reproducibility
	request_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=True)

	# CRYPTO: SHA-256 Hash of the log entry for tamper-evidence
	# We use a server_default for migration safety, but the app should always provide this.
	entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default='')

	# SEALING: Reference to the Block that cryptographically secures this log.
	# Null means the log is currently in the "Hot/Open" state and hasn't been sealed yet.
	block_id: Mapped[uuid.UUID | None] = mapped_column(
		ForeignKey('audit_blocks.id', ondelete='RESTRICT'), nullable=True, index=True
	)

	block: Mapped[AuditBlock | None] = relationship(back_populates='logs')

	# Composite Index for common dashboard filtering
	__table_args__ = (Index('ix_audit_project_time_decision', 'project_id', 'timestamp', 'decision'),)


class AuditBlock(Base, UUIDMixin, TimestampMixin, ProjectScopedMixin):
	"""
	Represents a sealed, cryptographically signed time-window of audit logs.
	This forms the "Blockchain" structure of the audit trail.

	Once logs are associated with a Block, they are considered immutable and "Sealed".
	"""

	__tablename__ = 'audit_blocks'

	# Monotonically increasing index per project (0, 1, 2...).
	# Allows easy ordering and gap detection.
	sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)

	# Cryptographic Link: SHA-256 hash of the previous block's header.
	# If the previous block is altered, this hash becomes invalid, breaking the chain.
	prev_block_hash: Mapped[str] = mapped_column(String(64), nullable=False)

	# Integrity Proof: The Root Hash of the Merkle Tree containing all logs in this block.
	merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)

	# Digital Signature of the Block Header (Index + PrevHash + Root + Time + Count)
	# Signed by the Ambyte System Private Key. Stored as Hex or Base64 string.
	signature: Mapped[str] = mapped_column(String, nullable=False)

	# Metadata
	timestamp_start: Mapped[datetime] = mapped_column(nullable=False)
	timestamp_end: Mapped[datetime] = mapped_column(nullable=False)
	log_count: Mapped[int] = mapped_column(Integer, nullable=False)

	# Relationships
	logs: Mapped[list[AuditLog]] = relationship(back_populates='block')

	# Ensure strict ordering per project
	__table_args__ = (UniqueConstraint('project_id', 'sequence_index', name='uq_project_block_sequence'),)

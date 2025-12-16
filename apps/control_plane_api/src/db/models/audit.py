from datetime import datetime
from typing import Any

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, UUIDMixin


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

	# Composite Index for common dashboard filtering:
	# "Show me all denials for this project in the last hour"
	__table_args__ = (Index('ix_audit_project_time_decision', 'project_id', 'timestamp', 'decision'),)

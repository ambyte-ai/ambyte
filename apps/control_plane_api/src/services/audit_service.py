import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.audit import AuditLog
from src.schemas.audit import AuditLogCreate
from src.services.audit_buffer import audit_buffer

logger = logging.getLogger(__name__)


class AuditService:
	"""
	Manages the write-path for Audit Logs.
	Supports both:
	  - Direct Postgres writes (used by background consumers)
	  - Redis Stream buffering (used by hot-path endpoints)
	"""  # noqa: E101

	# ==========================================================================
	# Redis Stream Buffer (Fast Path)
	# ==========================================================================

	@staticmethod
	async def log_to_buffer(project_id: UUID, entry: AuditLogCreate) -> str | None:
		"""
		Write a single audit entry to Redis Stream (fast path).
		Sub-millisecond latency, decoupled from database writes.

		Returns:
		    The stream entry ID, or None on error.
		"""  # noqa: E101
		return await audit_buffer.push(project_id, entry)

	@staticmethod
	async def log_batch_to_buffer(project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Bulk write audit entries to Redis Stream (fast path).
		Uses pipelining for maximum throughput.

		Returns:
		    Number of entries successfully buffered.
		"""  # noqa: E101
		return await audit_buffer.push_batch(project_id, entries)

	# ==========================================================================
	# Direct Postgres Writes (Slow Path - for Background Consumers)
	# ==========================================================================

	@staticmethod
	async def log_single(db: AsyncSession, project_id: UUID, entry: AuditLogCreate) -> AuditLog:
		"""
		Write a single audit entry directly to Postgres.
		Used by the Decision Engine synchronously (or via BackgroundTask).
		"""
		# Serialize ReasonTrace to dict for JSONB storage
		reason_trace_data = entry.reason_trace.model_dump() if entry.reason_trace else None

		db_obj = AuditLog(
			project_id=project_id,
			timestamp=entry.timestamp,
			actor_id=entry.actor_id,
			resource_urn=entry.resource_urn,
			action=entry.action,
			decision=entry.decision,
			reason_trace=reason_trace_data,
			request_context=entry.request_context,
		)
		db.add(db_obj)
		await db.commit()
		return db_obj

	@staticmethod
	async def log_batch(db: AsyncSession, project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Bulk write audit entries directly to Postgres.
		Used by the SDK background sync or bulk ingest endpoint.
		Returns the count of inserted rows.
		"""
		if not entries:
			return 0

		# Convert Pydantic -> DB Objects
		db_objects = [
			AuditLog(
				project_id=project_id,
				timestamp=entry.timestamp,
				actor_id=entry.actor_id,
				resource_urn=entry.resource_urn,
				action=entry.action,
				decision=entry.decision,
				reason_trace=entry.reason_trace.model_dump() if entry.reason_trace else None,
				request_context=entry.request_context,
			)
			for entry in entries
		]

		# Use bulk save for performance
		db.add_all(db_objects)
		await db.commit()

		count = len(db_objects)
		logger.info(f'Ingested {count} audit logs for project {project_id}')
		return count

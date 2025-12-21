import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.audit import AuditLog
from src.schemas.audit import AuditLogCreate

logger = logging.getLogger(__name__)


class AuditService:
	"""
	Manages the write-path for Audit Logs.
	"""

	@staticmethod
	async def log_single(db: AsyncSession, project_id: UUID, entry: AuditLogCreate) -> AuditLog:
		"""
		Write a single audit entry.
		Used by the Decision Engine synchronously (or via BackgroundTask).
		"""
		db_obj = AuditLog(
			project_id=project_id,
			timestamp=entry.timestamp,
			actor_id=entry.actor_id,
			resource_urn=entry.resource_urn,
			action=entry.action,
			decision=entry.decision,
			reason_trace=entry.reason_trace,
			request_context=entry.request_context,
		)
		db.add(db_obj)
		await db.commit()
		return db_obj

	@staticmethod
	async def log_batch(db: AsyncSession, project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Bulk write audit entries.
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
				reason_trace=entry.reason_trace,
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

import logging
from uuid import UUID

from ambyte_schemas.models.audit import AuditLogEntry, Decision
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from src.config import settings

# Import the Table definition from the API codebase
# This works because we share the monorepo context in the Docker build
from src.db.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditRepository:
	"""
	Async persistence layer for Audit Logs.
	Stateless insert operations for high-throughput batching.
	"""

	def __init__(self):
		self.engine: AsyncEngine | None = None

	async def connect(self):
		"""Initialize DB connection pool."""
		logger.info(f'Connecting to database: {settings.DATABASE_URL}')
		self.engine = create_async_engine(
			settings.DATABASE_URL,
			pool_size=10,
			max_overflow=20,
			echo=False,  # Keep logs clean in production
		)

	async def close(self):
		"""Dispose of connection pool."""
		if self.engine:
			await self.engine.dispose()

	@staticmethod
	def map_to_db_row(project_id: str, log: AuditLogEntry) -> dict:
		"""
		Convert Pydantic model to flat DB dictionary.
		"""
		decision_name = Decision(log.decision).name
		return {
			'id': log.id,
			'project_id': UUID(project_id),
			'timestamp': log.timestamp,
			'actor_id': log.actor.id,
			'resource_urn': log.resource_urn,
			'action': log.action,
			'decision': decision_name,  # Enum name (ALLOW/DENY)
			'reason_trace': (log.evaluation_trace.model_dump() if log.evaluation_trace else None),
			'request_context': log.request_context,
			'entry_hash': log.entry_hash,
		}

	async def insert_batch(self, entries: list[dict]) -> int:
		"""
		Commit a batch of rows to the database.
		Returns: Number of rows inserted.
		"""
		if not entries:
			return 0

		assert self.engine is not None, 'DB connection not initialized'
		try:
			async with self.engine.begin() as conn:
				# Use Postgres specific insert for ON CONFLICT support
				stmt = pg_insert(AuditLog).values(entries)

				# Idempotency: If ID exists, do nothing.
				# This handles at-least-once delivery duplicates from Redis.
				stmt = stmt.on_conflict_do_nothing(index_elements=['id'])

				await conn.execute(stmt)

			logger.info(f'Flushed {len(entries)} logs to Postgres.')
			return len(entries)

		except Exception as e:
			# Critical failure: If DB is down, the caller must handle retry/crash.
			logger.error(f'Failed to flush audit batch: {e}')
			raise e

"""
High-speed Redis Stream buffer for audit log ingestion.
Decouples ingestion latency from database/signing operations.
"""

import logging
from typing import Any
from uuid import UUID

from src.core.cache import cache
from src.schemas.audit import AuditLogCreate

logger = logging.getLogger(__name__)

# Maximum stream length before automatic trimming (approximate)
# Prevents unbounded memory growth while maintaining ~24h of logs at high volume
DEFAULT_MAXLEN = 100_000


class AuditBuffer:
	"""
	Writes audit logs to Redis Stream for async processing.
	Enables sub-millisecond ingestion by decoupling from Postgres writes.

	Stream Key Format: audit:logs:{project_id}

	Entry Format (flat string fields for Redis):
	{
	    "data": <JSON serialized AuditLogCreate>,
	    "timestamp": <ISO timestamp as string>
	}
	"""  # noqa: E101

	@staticmethod
	def _stream_key(project_id: UUID) -> str:
		"""Generate the stream key for a project."""
		return f'audit:logs:{project_id}'

	@staticmethod
	def _serialize_entry(entry: AuditLogCreate) -> dict[str, Any]:
		"""
		Serialize an AuditLogCreate to a flat dict for Redis Stream storage.
		Redis Streams require string values, so we JSON-encode the full entry.
		"""
		return {
			'data': entry.model_dump_json(exclude_none=True),
			'ts': entry.timestamp.isoformat(),
		}

	async def push(self, project_id: UUID, entry: AuditLogCreate) -> str | None:
		"""
		Push a single audit entry to the Redis Stream.

		Args:
		    project_id: The tenant project UUID
		    entry: The audit log entry to buffer

		Returns:
		    The stream entry ID (e.g., "1704067200000-0"), or None on error.
		"""  # noqa: E101
		stream_key = self._stream_key(project_id)
		fields = self._serialize_entry(entry)

		entry_id = await cache.xadd(stream_key, fields, maxlen=DEFAULT_MAXLEN)

		if entry_id:
			logger.debug(f'Buffered audit log {entry_id} to {stream_key}')
		else:
			logger.warning(f'Failed to buffer audit log to {stream_key}')

		return entry_id

	async def push_batch(self, project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Push multiple audit entries to the Redis Stream using pipelining.
		Significantly faster than individual push() calls for bulk ingestion.

		Args:
		    project_id: The tenant project UUID
		    entries: List of audit log entries to buffer

		Returns:
		    Number of entries successfully buffered.
		"""  # noqa: E101
		if not entries:
			return 0

		stream_key = self._stream_key(project_id)
		serialized = [self._serialize_entry(e) for e in entries]

		count = await cache.xadd_pipeline(stream_key, serialized, maxlen=DEFAULT_MAXLEN)

		logger.info(f'Buffered {count}/{len(entries)} audit logs to {stream_key}')
		return count

	async def get_stream_length(self, project_id: UUID) -> int:
		"""Get the current number of buffered entries for a project."""
		stream_key = self._stream_key(project_id)
		return await cache.xlen(stream_key)


# Singleton instance
audit_buffer = AuditBuffer()

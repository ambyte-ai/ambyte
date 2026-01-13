import logging
from typing import Any, TypeVar, cast

from pydantic import BaseModel
from redis.asyncio import Redis, from_url
from src.core.config import settings

logger = logging.getLogger(__name__)

# Generic type for Pydantic models
T = TypeVar('T', bound=BaseModel)


class CacheService:
	"""
	Async wrapper around Redis for caching Policy decisions.
	Handles Pydantic serialization/deserialization automatically.
	Also provides Redis Streams support for high-speed buffering.
	"""

	def __init__(self):
		self._redis: Redis | None = None

	async def connect(self):
		"""
		Initialize the Redis connection pool.
		Should be called in the FastAPI lifespan startup.
		"""
		if not self._redis:
			logger.info(f'Connecting to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}')
			self._redis = from_url(
				settings.REDIS_URL,
				encoding='utf-8',
				decode_responses=True,
				socket_connect_timeout=5.0,
				socket_timeout=5.0,
			)

			try:
				await self._redis.ping()
				logger.info('✅ Redis connection established and verified.')
			except Exception as e:
				logger.critical(f'❌ Redis connection FAILED: {e}')
				raise e

	async def close(self):
		"""Close connection pool."""
		if self._redis:
			await self._redis.close()

	async def get_model(self, key: str, model_cls: type[T]) -> T | None:
		"""
		Retrieve a JSON object from cache and parse it into a Pydantic model.
		"""
		if not self._redis:
			return None

		try:
			data = await self._redis.get(key)
			if data:
				return model_cls.model_validate_json(data)
		except Exception as e:
			# We fail open (return None) so the app falls back to DB/Compute
			logger.warning(f'Cache GET error for {key}: {e}')
		return None

	async def set_model(self, key: str, model: BaseModel, ttl_seconds: int = 300):
		"""
		Serialize a Pydantic model to JSON and store it.
		Default TTL: 5 minutes.
		"""
		if not self._redis:
			return

		try:
			# exclude_none=True saves space, but make sure your models handle missing fields gracefully
			json_data = model.model_dump_json(exclude_none=True)
			await self._redis.set(key, json_data, ex=ttl_seconds)
		except Exception as e:
			logger.warning(f'Cache SET error for {key}: {e}')

	async def delete_pattern(self, pattern: str):
		"""
		Invalidate keys matching a pattern.
		Used when a Policy or Resource is updated.
		Note: SCAN is O(N) but safer than KEYS in production.
		"""
		if not self._redis:
			return

		try:
			# Create a cursor-based iterator
			keys = []
			async for key in self._redis.scan_iter(match=pattern):
				keys.append(key)

			if keys:
				await self._redis.delete(*keys)
				logger.info(f"Invalidated {len(keys)} cache keys matching '{pattern}'")
		except Exception as e:
			logger.error(f"Cache invalidation failed for '{pattern}': {e}")

	# ==========================================================================
	# Redis Streams Support (for Audit Log Buffering)
	# ==========================================================================

	async def xadd(
		self, stream: str, fields: dict[str, Any], maxlen: int | None = None, approximate: bool = True
	) -> str | None:
		"""
		Add an entry to a Redis Stream.

		Args:
		    stream: The stream key (e.g., "audit:logs:{project_id}")
		    fields: Dictionary of field-value pairs to store
		    maxlen: Optional max stream length (for automatic trimming)
		    approximate: If True, uses ~ for more efficient trimming

		Returns:
		    The auto-generated entry ID (timestamp-based), or None on error.
		"""  # noqa: E101
		if not self._redis:
			return None

		try:
			entry_id = await self._redis.xadd(stream, cast(Any, fields), maxlen=maxlen, approximate=approximate)
			return entry_id
		except Exception as e:
			logger.error(f'Stream XADD error for {stream}: {e}')
			return None

	async def xadd_pipeline(self, stream: str, entries: list[dict[str, Any]], maxlen: int | None = None) -> int:
		"""
		Batch add multiple entries to a Redis Stream using pipelining.
		Significantly faster than individual XADD calls for bulk ingestion.

		Args:
		    stream: The stream key
		    entries: List of field dictionaries to add
		    maxlen: Optional max stream length

		Returns:
		    Number of entries successfully added.
		"""  # noqa: E101
		if not self._redis or not entries:
			return 0

		try:
			async with self._redis.pipeline(transaction=False) as pipe:
				for fields in entries:
					pipe.xadd(stream, cast(Any, fields), maxlen=maxlen, approximate=True)
				results = await pipe.execute()
			# Count successful additions (non-None results)
			return sum(1 for r in results if r is not None)
		except Exception as e:
			logger.error(f'Stream XADD pipeline error for {stream}: {e}')
			return 0

	async def xlen(self, stream: str) -> int:
		"""Get the number of entries in a stream."""
		if not self._redis:
			return 0
		try:
			return await self._redis.xlen(stream)
		except Exception as e:
			logger.warning(f'Stream XLEN error for {stream}: {e}')
			return 0

	@property
	def client(self) -> Redis:
		"""Raw client access if needed."""
		if not self._redis:
			raise RuntimeError('Redis client not initialized. Call connect() first.')
		return self._redis


# Singleton instance
cache = CacheService()

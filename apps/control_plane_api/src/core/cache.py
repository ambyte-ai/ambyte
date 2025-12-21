import logging
from typing import TypeVar

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
			self._redis = from_url(settings.REDIS_URL, encoding='utf-8', decode_responses=True)

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

	@property
	def client(self) -> Redis:
		"""Raw client access if needed."""
		if not self._redis:
			raise RuntimeError('Redis client not initialized. Call connect() first.')
		return self._redis


# Singleton instance
cache = CacheService()

import logging
from datetime import timedelta
from typing import Any

from ingest_worker.config import settings
from ingest_worker.schemas.ingest import IngestJobResponse, IngestStatus
from redis.asyncio import Redis, from_url

logger = logging.getLogger(__name__)


class JobStore:
	"""
	Redis-backed persistence layer for Ingestion Jobs.
	Replaces the in-memory 'job_store' dictionary to allow state to survive
	container restarts and be shared between the API and Worker processes.
	"""

	def __init__(self):
		self._redis: Redis | None = None
		# Jobs expire after 24 hours to prevent memory leaks in Redis
		self.job_ttl = timedelta(hours=24)

	async def initialize(self):
		"""
		Creates the Redis connection pool.
		Should be called during application startup (lifespan).
		"""
		if not self._redis:
			redis_url = settings.REDIS_JOB_STORE_URL
			logger.info(f'Connecting to Job Store at {redis_url}')
			self._redis = from_url(redis_url, encoding='utf-8', decode_responses=True)

	async def close(self):
		"""Closes the connection pool."""
		if self._redis:
			await self._redis.close()

	def _key(self, job_id: str) -> str:
		"""Namespaces the keys."""
		return f'ambyte:jobs:{job_id}'

	async def create_job(self, job_id: str, filename: str = 'Unknown Document') -> IngestJobResponse:
		"""
		Initializes a new job entry with status QUEUED.
		"""
		job = IngestJobResponse(
			job_id=job_id, status=IngestStatus.QUEUED, message='Job created and queued.', stats={'filename': filename}
		)
		await self._save(job)
		return job

	async def get_job(self, job_id: str) -> IngestJobResponse | None:
		"""
		Retrieves job state. Returns None if not found.
		"""
		if not self._redis:
			raise RuntimeError('JobStore not initialized')

		raw_data = await self._redis.get(self._key(job_id))
		if not raw_data:
			return None

		try:
			return IngestJobResponse.model_validate_json(raw_data)
		except Exception as e:
			logger.error(f'Corrupt job data for {job_id}: {e}')
			return None

	async def update_status(self, job_id: str, status: IngestStatus, message: str | None = None):
		"""
		Updates the lifecycle status of a job.
		"""
		job = await self.get_job(job_id)
		if job:
			job.status = status
			if message:
				job.message = message
			await self._save(job)

	async def set_result(self, job_id: str, stats: dict[str, Any]):
		"""
		Marks job as COMPLETED and attaches result statistics.
		"""
		job = await self.get_job(job_id)
		if job:
			job.status = IngestStatus.COMPLETED
			job.stats.update(stats)
			job.message = 'Ingestion successful'
			await self._save(job)

	async def set_error(self, job_id: str, error_message: str):
		"""
		Marks job as FAILED and attaches error details.
		"""
		job = await self.get_job(job_id)
		if job:
			job.status = IngestStatus.FAILED
			job.message = error_message
			await self._save(job)

	async def _save(self, job: IngestJobResponse):
		"""
		Internal helper to write the Pydantic model to Redis.
		"""
		if not self._redis:
			raise RuntimeError('JobStore not initialized')

		# Serializing to JSON allows us to store complex nested dicts (stats) easily
		data = job.model_dump_json()
		await self._redis.set(self._key(job.job_id), data, ex=self.job_ttl)


# Singleton instance
job_store = JobStore()

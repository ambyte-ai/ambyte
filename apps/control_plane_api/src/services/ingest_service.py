import json
import logging
from uuid import UUID

from src.core.cache import cache
from src.schemas.ingest import IngestJobRead, IngestStatus

logger = logging.getLogger(__name__)


class IngestService:
	"""
	Read-only service to fetch the status of background ingestion jobs.
	Reads directly from the shared Redis state used by the Ingest Worker.
	"""

	@staticmethod
	async def get_recent_jobs(project_id: UUID, limit: int = 50) -> list[IngestJobRead]:
		"""
		Retrieves the most recent ingestion jobs from Redis.

		Since the Ingest Worker operates largely asynchronously, it writes state
		to Redis keys formatted as 'ambyte:jobs:{uuid}'. This method scans those keys
		to populate the dashboard UI.

		Args:
		    project_id: Context UUID (currently used for logging/future filtering).
		    limit: Max number of jobs to return.

		Returns:
		    A list of IngestJobRead models, sorted with active jobs first.
		"""  # noqa: E101
		if not cache.client:
			logger.warning('Redis client not available for IngestService.')
			return []

		jobs: list[IngestJobRead] = []

		# 1. Scan for job keys
		# We scan for keys matching the pattern defined in the worker's job_store.py
		# Note: SCAN is safe for production (doesn't block like KEYS)
		keys: list[str] = []
		async for key in cache.client.scan_iter(match='ambyte:jobs:*', count=100):
			keys.append(key)
			# Fetch a buffer to account for potential parsing errors or filtering
			if len(keys) >= limit * 2:
				break

		if not keys:
			return []

		# 2. Batch fetch values (MGET is efficient)
		try:
			raw_values = await cache.client.mget(keys)
		except Exception as e:
			logger.error(f'Failed to fetch job data from Redis: {e}')
			return []

		# 3. Deserialize and Validate
		for raw in raw_values:
			if not raw:
				continue

			try:
				# The worker stores data as a JSON string
				data = json.loads(raw)

				# Basic validation: ensure it looks like a job
				if 'job_id' not in data or 'status' not in data:
					continue

				# Map to Pydantic schema
				job = IngestJobRead.model_validate(data)
				jobs.append(job)

			except (json.JSONDecodeError, ValueError) as e:
				logger.debug(f'Skipping corrupt job entry: {e}')
				continue

		# 4. Sorting Heuristic
		# Since the Redis keys don't strictly guarantee insertion order and we lack
		# a high-precision timestamp in the root schema, we sort by 'Liveness'.
		# Active jobs appear at the top, followed by Completed/Failed ones.
		def sort_key(j: IngestJobRead):
			is_active = j.status not in [IngestStatus.COMPLETED, IngestStatus.FAILED]
			# Tuple sort: Active (0) < Inactive (1), then job_id as tiebreaker
			return (not is_active, j.job_id)

		jobs.sort(key=sort_key)

		return jobs[:limit]

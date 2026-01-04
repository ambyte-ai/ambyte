import logging
import os
import sys
import tempfile
from typing import Any

import httpx
import openai
from arq import Retry
from arq.connections import RedisSettings
from ingest_worker.config import settings
from ingest_worker.schemas.ingest import IngestStatus
from ingest_worker.services.definition_extractor import DefinitionExtractor
from ingest_worker.services.job_store import job_store
from ingest_worker.services.obligation_extractor import ObligationExtractor
from ingest_worker.services.pipeline import IngestionPipeline
from ingest_worker.services.storage import blob_storage

# Configure logging for the standalone worker process
logging.basicConfig(
	level=settings.log_level_value,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ==============================================================================
# Retry Configuration
# ==============================================================================

# Errors that should trigger a retry with exponential backoff
RETRYABLE_ERRORS = (
	# Network/HTTP issues
	httpx.NetworkError,
	httpx.TimeoutException,
	ConnectionError,
	TimeoutError,
	OSError,  # Includes socket errors
	# OpenAI specific
	openai.RateLimitError,
	openai.APIConnectionError,
	openai.APITimeoutError,
	openai.InternalServerError,
)

# Errors that should fail immediately (no point retrying)
NON_RETRYABLE_ERRORS = (
	ValueError,  # Malformed PDF, bad input
	KeyError,  # Missing required fields
	TypeError,  # Programming errors
	openai.AuthenticationError,  # Bad API key won't fix itself
	openai.BadRequestError,  # Invalid request parameters
)

# ==============================================================================
# Job Execution Logic
# ==============================================================================


async def run_ingest_pipeline(
	ctx: dict, job_id: str, s3_key: str, s3_uri: str, filename: str, project_id: str | None
) -> dict[str, Any]:
	"""
	The core task function executed by the worker.

	Args:
	    ctx: ARQ context dictionary (contains initialized pipeline).
	    job_id: Unique UUID for tracking.
	    s3_key: Storage key (e.g. "{job_id}.pdf").
	    s3_uri: Full URI for reference (s3://bucket/key).
	    filename: Original filename for metadata.
	    project_id: Optional tenant/project scope.
	"""  # noqa: E101
	pipeline: IngestionPipeline = ctx['pipeline']

	# Determine a local temporary path for processing
	# ARQ workers have their own ephemeral filesystem

	# We use tempfile to ensure secure, collision-free paths
	with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
		local_file_path = tmp.name

	logger.info(f'[{job_id}] Worker received job. Downloading from {s3_uri}...')

	# 1. Update State -> PROCESSING
	await job_store.update_status(job_id, IngestStatus.PARSING, message='Downloading document...')

	try:
		# 2. Download from S3
		await blob_storage.download_file(s3_key, local_file_path)

		# 3. Execute the Heavy Lifting
		# Note: we pass the file path directly. The pipeline's parser will open it.
		stats = await pipeline.run(
			file=local_file_path,
			filename=filename,
			job_id=job_id,
			project_id=project_id,
			s3_key=s3_key,
		)

		# 3. Update State -> SUCCESS
		await job_store.set_result(job_id, stats)
		logger.info(f'[{job_id}] Job completed successfully.')
		return stats

	except NON_RETRYABLE_ERRORS as e:
		# Non-retryable errors: fail immediately
		logger.error(f'[{job_id}] Job failed (non-retryable): {e}', exc_info=True)
		await job_store.set_error(job_id, f'Permanent failure: {e}')
		raise  # Let ARQ record the failure

	except RETRYABLE_ERRORS as e:
		# Retryable errors: signal ARQ to retry with backoff
		job_try = ctx.get('job_try', 1)
		max_tries = 4
		if job_try < max_tries:
			delay = 2**job_try * 10  # Exponential backoff: 20s, 40s, 80s
			logger.warning(f'[{job_id}] Retryable error (attempt {job_try}/{max_tries}): {e}. Retrying in {delay}s...')
			await job_store.update_status(job_id, IngestStatus.QUEUED, f'Retry {job_try}/{max_tries} scheduled...')
			raise Retry(defer=delay) from e
		else:
			# Exhausted retries
			logger.error(f'[{job_id}] Job failed after {max_tries} attempts: {e}')
			await job_store.set_error(job_id, f'Failed after {max_tries} retries: {e}')
			raise

	except Exception as e:
		# Unknown errors: fail but log for investigation
		logger.error(f'[{job_id}] Job failed with unexpected error: {e}', exc_info=True)
		await job_store.set_error(job_id, str(e))
		raise

	finally:
		# 5. Cleanup: Remove the temp file
		# We do this regardless of success or failure to prevent disk exhaustion.
		if os.path.exists(local_file_path):
			try:
				os.remove(local_file_path)
				logger.debug(f'[{job_id}] Cleaned up temp file: {local_file_path}')
			except OSError as cleanup_err:
				logger.warning(f'[{job_id}] Failed to delete temp file: {cleanup_err}')


# ==============================================================================
# Lifecycle Hooks
# ==============================================================================


async def startup(ctx: dict):
	"""
	Called when the worker process boots up.
	Initialize DB connections here to persist them across jobs.
	"""
	logger.info('Initializing Worker resources...')

	# Initialize Redis Job Store connection
	await job_store.initialize()

	# Initialize Blob Storage (MinIO/S3)
	blob_storage.initialize()

	# Initialize the Pipeline (Connects to Qdrant, verifies schemas)
	pipeline = IngestionPipeline()
	await pipeline.initialize()

	# Initialize External Clients (Instructor, VoyageAI)
	# This ensures we reuse connection pools across jobs
	logger.info('Initializing LLM & Embedding clients...')
	pipeline.def_extractor = DefinitionExtractor()  # Re-init to grab fresh client if needed
	pipeline.rule_extractor = ObligationExtractor()
	# VoyageAI client manages its own connection pool internally
	# we just ensure the service is ready

	# Store in context for access inside jobs
	ctx['pipeline'] = pipeline
	logger.info('Worker resources ready.')


async def shutdown(ctx: dict):
	"""
	Called when the worker process shuts down.
	Gracefully close connections.
	"""
	logger.info('Shutting down Worker resources...')

	await job_store.close()
	blob_storage.close()


# ==============================================================================
# ARQ Configuration
# ==============================================================================


class WorkerSettings:
	"""
	Configuration class used by 'arq ingest_worker.worker.WorkerSettings'
	"""

	# Functions to register
	functions = [run_ingest_pipeline]

	# Lifecycle hooks
	on_startup = startup
	on_shutdown = shutdown

	# Connection Settings
	# Use the shared REDIS_JOB_STORE_URL from config
	redis_settings = RedisSettings.from_dsn(settings.REDIS_JOB_STORE_URL)

	# Concurrency Control
	# Limit to 2 concurrent jobs per worker container to prevent
	# OOM kills (PDF parsing is memory heavy) and API Rate Limiting.
	max_jobs = 2

	# Job Timeout (10 minutes) - large legal docs can take time
	job_timeout = 600

	# Retry Configuration
	# Max retries handled in job logic via Retry exception
	# This is the global default; we handle per-error retries manually
	max_tries = 4
	retry_jobs = True

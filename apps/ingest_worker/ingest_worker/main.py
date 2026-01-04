import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import (
	FastAPI,
	File,
	Form,
	HTTPException,
	UploadFile,
	status,
)
from fastapi.concurrency import run_in_threadpool
from ingest_worker.config import settings
from ingest_worker.extractors.chunker import SectionChunker
from ingest_worker.extractors.pdf_parser import PdfParser
from ingest_worker.schemas.ingest import (
	DocumentChunk,
	IngestJobResponse,
)
from ingest_worker.services.job_store import job_store
from ingest_worker.services.storage import blob_storage

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('ambyte-ingest')

# ==============================================================================
# Global State
# ==============================================================================

# ARQ Redis connection pool for enqueuing jobs
redis_pool: ArqRedis | None = None


# ==============================================================================
# Lifecycle & Background Logic
# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""
	Application startup/shutdown hooks.
	Initializes Redis pool for job enqueueing.
	"""
	global redis_pool
	try:
		# Connect to Redis for job queue
		redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_JOB_STORE_URL))
		await job_store.initialize()

		# Initialize S3 Connection
		blob_storage.initialize()

		logger.info('Ingest API ready. Redis pool initialized.')
		yield
	except Exception as e:
		logger.critical(f'Failed to initialize Ingest Worker: {e}')
		raise
	finally:
		if redis_pool:
			await redis_pool.close()
		await job_store.close()


# ==============================================================================
# API Definition
# ==============================================================================

app = FastAPI(
	title='Ambyte Ingest Worker',
	version='0.1.0',
	description='Vector ingestion service for legal documents.',
	lifespan=lifespan,
)


@app.get('/health')
def health_check():
	"""K8s/Docker health probe."""
	return {'status': 'ok', 'service': 'ingest-worker'}


def _save_to_disk(source_file, dest_path: str):
	with open(dest_path, 'wb') as buffer:
		shutil.copyfileobj(source_file, buffer)


@app.post(
	'/v1/ingest',
	response_model=IngestJobResponse,
	status_code=status.HTTP_202_ACCEPTED,
	summary='Async Ingest (Upload & Index)',
	description='Uploads a file for background processing. Returns a Job ID to poll.',
)
async def trigger_ingestion(
	file: Annotated[UploadFile, File(description='PDF Document')],
	project_id: Annotated[str | None, Form(description='Project context for these policies')] = None,
):
	"""
	1. Spools file to disk (safe for large PDFs).
	2. Enqueues job to ARQ worker.
	3. Returns Job ID immediately.
	"""
	if redis_pool is None:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Job queue not available.',
		)

	if file.content_type != 'application/pdf':
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unsupported type: {file.content_type}. Only 'application/pdf'.",
		)

	job_id = str(uuid.uuid4())
	filename = file.filename or 'unknown.pdf'

	try:
		# 1. Upload Stream to S3
		# We use the job_id as the key for simplicity and uniqueness
		s3_key = f'{job_id}.pdf'
		s3_uri = await blob_storage.upload_stream(file_obj=file.file, key=s3_key, content_type=file.content_type)

		# 2. Initialize Job State
		job_info = await job_store.create_job(job_id)

		# 3. Enqueue job to ARQ worker process
		# Instead of a file path, we pass the S3 Key and URI
		await redis_pool.enqueue_job(
			'run_ingest_pipeline',
			job_id=job_id,
			s3_key=s3_key,
			s3_uri=s3_uri,
			filename=filename,
			project_id=project_id,
		)

		logger.info(f'[{job_id}] Enqueued ingestion job for {filename}')
		return job_info

	except Exception as e:
		logger.error(f'Failed to queue ingestion: {e}')
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail='Could not accept file upload.',
		) from e
	finally:
		await file.close()


@app.get(
	'/v1/ingest/{job_id}',
	response_model=IngestJobResponse,
	summary='Get Job Status',
)
async def get_job_status(job_id: str):
	"""
	Poll this endpoint to check if parsing/indexing is complete.
	"""
	job = await job_store.get_job(job_id)
	if job is None:
		raise HTTPException(status_code=404, detail='Job not found')
	return job


# ==============================================================================
# Debug / Phase 1 Endpoints
# ==============================================================================

# We initialize these locally just for the debug endpoint usage
# The main pipeline manages its own instances.
_debug_parser = PdfParser()
_debug_chunker = SectionChunker(max_tokens=1000)


@app.post(
	'/v1/ingest/preview',
	response_model=list[DocumentChunk],
	summary='Synchronous Parse & Chunk (Debug)',
	description='Debug tool: Returns raw chunks without embedding/indexing.',
)
async def preview_ingest(
	file: Annotated[UploadFile, File(description='PDF to parse')],
):
	if file.content_type != 'application/pdf':
		raise HTTPException(status_code=400, detail='Only PDF supported')

	filename = file.filename or 'unknown.pdf'
	try:
		# Direct parsing (Blocking wait)
		elements = await run_in_threadpool(_debug_parser.parse, file.file, filename)
		chunks = _debug_chunker.chunk(elements, filename=filename)
		return chunks
	except Exception as e:
		logger.error(f'Preview failed: {e}')
		raise HTTPException(status_code=500, detail=str(e)) from e
	finally:
		await file.close()

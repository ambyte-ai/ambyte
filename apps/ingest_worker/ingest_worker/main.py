import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import (
	BackgroundTasks,
	FastAPI,
	File,
	Form,
	HTTPException,
	UploadFile,
	status,
)
from fastapi.concurrency import run_in_threadpool
from ingest_worker.extractors.chunker import SectionChunker
from ingest_worker.extractors.pdf_parser import PdfParser
from ingest_worker.schemas.ingest import (
	DocumentChunk,
	IngestJobResponse,
	IngestStatus,
)
from ingest_worker.services.pipeline import IngestionPipeline

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('ambyte-ingest')

# ==============================================================================
# Global State
# ==============================================================================

# The Orchestrator
pipeline = IngestionPipeline()

# In-Memory Job Store (MVP)
# In production, replace this with Redis/Postgres # TODO
job_store: dict[str, IngestJobResponse] = {}


# ==============================================================================
# Lifecycle & Background Logic
# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""
	Application startup/shutdown hooks.
	Ensures the Vector Database schema exists before accepting requests.
	"""
	try:
		await pipeline.initialize()
		yield
	except Exception as e:
		logger.critical(f'Failed to initialize Ingest Worker: {e}')
		raise


async def background_ingest_task(job_id: str, temp_file_path: str, filename: str, project_id: str | None):
	"""
	The actual worker logic running in the background.
	"""
	logger.info(f'[{job_id}] Started background processing for {filename}')

	# Update status to processing
	if job_id in job_store:
		job_store[job_id].status = IngestStatus.PARSING

	try:
		# Run the full Parsing -> Chunking -> Embedding -> Qdrant pipeline
		# Note: We pass the path directly so the parsing (CPU bound) step
		# can handle file opening in its own threadpool/process rather than blocking here.
		stats = await pipeline.run(
			file=temp_file_path,
			filename=filename,
			job_id=job_id,
			project_id=project_id,
		)

		# Update Success State
		if job_id in job_store:
			job_store[job_id].status = IngestStatus.COMPLETED
			job_store[job_id].stats = stats
			job_store[job_id].message = 'Ingestion successful'

	except Exception as e:
		logger.error(f'[{job_id}] Background task failed: {e}', exc_info=True)
		if job_id in job_store:
			job_store[job_id].status = IngestStatus.FAILED
			job_store[job_id].message = str(e)

	finally:
		# Cleanup: Remove the temporary file to save disk space
		try:
			if os.path.exists(temp_file_path):
				os.remove(temp_file_path)
				logger.debug(f'[{job_id}] Cleaned up temp file {temp_file_path}')
		except Exception as cleanup_err:
			logger.warning(f'[{job_id}] Failed to cleanup temp file: {cleanup_err}')


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
	background_tasks: BackgroundTasks,
	file: Annotated[UploadFile, File(description='PDF Document')],
	project_id: Annotated[str | None, Form(description='Project context for these policies')] = None,
):
	"""
	1. Spools file to disk (safe for large PDFs).
	2. Spawns background task.
	3. Returns Job ID immediately.
	"""

	if file.content_type != 'application/pdf':
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unsupported type: {file.content_type}. Only 'application/pdf'.",
		)

	job_id = str(uuid.uuid4())
	filename = file.filename or 'unknown.pdf'

	try:
		# Create a temp file to persist the upload for the background worker
		# We cannot pass UploadFile directly to background tasks as it closes
		# when the request ends.
		fd, temp_path = tempfile.mkstemp(suffix='.pdf')
		os.close(fd)  # Close the low-level handle, we will write via python file obj

		# Stream copy to temp location (in threadpool to avoid blocking)
		await run_in_threadpool(_save_to_disk, file.file, temp_path)

		# Initialize Job State
		job_info = IngestJobResponse(
			job_id=job_id,
			status=IngestStatus.QUEUED,
			message='File accepted for processing.',
		)
		job_store[job_id] = job_info

		# Schedule the work
		background_tasks.add_task(
			background_ingest_task,
			job_id=job_id,
			temp_file_path=temp_path,
			filename=filename,
			project_id=project_id,
		)

		logger.info(f'[{job_id}] Queued ingestion for {filename}')
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
	if job_id not in job_store:
		raise HTTPException(status_code=404, detail='Job not found')
	return job_store[job_id]


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

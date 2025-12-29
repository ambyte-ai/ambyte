import logging
import time
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from ingest_worker.extractors.chunker import SectionChunker
from ingest_worker.extractors.pdf_parser import PdfParser
from ingest_worker.schemas.ingest import DocumentChunk

# Configure logging for the worker
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('ambyte-ingest')

app = FastAPI(
	title='Ambyte Ingest Worker',
	version='0.1.0',
	description='High-fidelity PDF parsing and semantic chunking service.',
)

# Initialize singletons
# In a real cluster, these might be configured via env vars
pdf_parser = PdfParser()
section_chunker = SectionChunker(max_tokens=1000)


@app.get('/health')
def health_check():
	"""K8s/Docker health probe."""
	return {'status': 'ok', 'service': 'ingest-worker'}


@app.post(
	'/v1/ingest/preview',
	response_model=list[DocumentChunk],
	summary='Synchronous Parse & Chunk (Debug)',
	description='Upload a PDF to see how it is parsed and chunked. Useful for verifying OCR quality and section logic.',
)
async def preview_ingest(file: Annotated[UploadFile, File(description='The legal document (PDF) to parse')]):
	"""
	1. Receives file stream.
	2. Runs 'unstructured' hi_res partitioning (CPU intensive).
	3. Runs semantic chunking.
	4. Returns JSON objects.
	"""
	if file.content_type != 'application/pdf':
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unsupported content type: {file.content_type}. Only 'application/pdf' supported in Phase 1.",
		)

	start_time = time.time()
	filename = file.filename or 'unknown.pdf'
	logger.info(f'Received upload: {filename}')

	try:
		# 1. PARSING (Heavy CPU)
		# We run this in a threadpool to avoid blocking the asyncio event loop
		# pass the file.file (SpooledTemporaryFile) directly
		elements = await run_in_threadpool(pdf_parser.parse, file.file, filename)

		parse_duration = time.time() - start_time
		logger.info(f'Parsed {len(elements)} elements in {parse_duration:.2f}s')

		# 2. CHUNKING (Light CPU)
		chunks = section_chunker.chunk(elements, filename=filename)

		total_duration = time.time() - start_time
		logger.info(f'Generated {len(chunks)} chunks. Total time: {total_duration:.2f}s')

		return chunks

	except ValueError as e:
		logger.error(f'Parsing logic error: {e}')
		raise HTTPException(status_code=422, detail=str(e)) from e
	except Exception as e:
		logger.error(f'Unexpected system error: {e}', exc_info=True)
		raise HTTPException(status_code=500, detail='Internal processing error during ingestion.') from e
	finally:
		await file.close()

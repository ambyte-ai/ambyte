import logging
import time
from typing import Any, BinaryIO

from fastapi.concurrency import run_in_threadpool
from ingest_worker.extractors.chunker import SectionChunker
from ingest_worker.extractors.pdf_parser import PdfParser
from ingest_worker.intelligence.embedding import EmbeddingService
from ingest_worker.intelligence.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
	"""
	Orchestrates the conversion of raw documents into indexed vectors.
	"""

	def __init__(self):
		# Phase 1 Components (CPU Bound)
		self.parser = PdfParser()
		# Max tokens set slightly lower than embedding model limit (1024 for Voyage)
		# to leave room for metadata injection if needed later.
		self.chunker = SectionChunker(max_tokens=800)

		# Phase 2 Components (IO/Network Bound)
		self.embedder = EmbeddingService()
		self.vector_store = VectorStore()

	async def initialize(self):
		"""
		Lifecycle hook: Run on app startup to ensure DB schema exists.
		"""
		logger.info('Initializing Ingestion Pipeline...')
		await self.vector_store.ensure_collection()
		logger.info('Ingestion Pipeline Ready.')

	async def run(
		self,
		file: BinaryIO | str,
		filename: str,
		job_id: str,
		project_id: str | None = None,
	) -> dict[str, Any]:
		"""
		Executes the full pipeline for a single document.

		Args:
		    file: The binary file stream OR a string file path.
		    filename: Original filename.
		    job_id: Unique trace ID for this process.
		    project_id: Optional tenant ID.

		Returns:
		    Dictionary containing execution stats.
		"""  # noqa: E101
		start_time = time.time()
		logger.info(f'[{job_id}] Starting ingestion for: {filename}')

		try:
			# ------------------------------------------------------------------
			# Step 1: Parsing (CPU Intensive)
			# ------------------------------------------------------------------
			# We offload this to a threadpool so we don't block the AsyncIO loop
			# used by other requests (like health checks or status queries).
			parse_start = time.time()
			elements = await run_in_threadpool(self.parser.parse, file, filename)

			if not elements:
				logger.warning(f'[{job_id}] No text extracted from file.')
				return {'status': 'empty_file', 'chunks': 0}

			logger.info(f'[{job_id}] Parsed {len(elements)} elements in {time.time() - parse_start:.2f}s')

			# ------------------------------------------------------------------
			# Step 2: Chunking (CPU - Fast)
			# ------------------------------------------------------------------
			# Chunking is usually fast enough to run in the main thread,
			# but if documents are massive (>500 pages), consider threadpool here too.
			chunks = self.chunker.chunk(elements, filename)
			logger.info(f'[{job_id}] Generated {len(chunks)} semantic chunks')

			if not chunks:
				return {'status': 'no_chunks_generated', 'chunks': 0}

			# ------------------------------------------------------------------
			# Step 3: Embedding (IO Bound - Network)
			# ------------------------------------------------------------------
			embed_start = time.time()

			# Extract just the content strings for the API
			texts = [c.content for c in chunks]
			vectors = await self.embedder.embed_documents(texts)

			logger.info(f'[{job_id}] Generated {len(vectors)} embeddings in {time.time() - embed_start:.2f}s')

			# ------------------------------------------------------------------
			# Step 4: Indexing (IO Bound - DB)
			# ------------------------------------------------------------------
			index_start = time.time()
			upserted_count = await self.vector_store.upsert_chunks(
				job_id=job_id,
				project_id=project_id,
				chunks=chunks,
				vectors=vectors,
			)

			index_duration = time.time() - index_start
			total_duration = time.time() - start_time
			logger.info(
				f'[{job_id}] Indexing complete in {index_duration:.2f}s. Upserted {upserted_count} points.\n'
				f'[{job_id}] Total Duration: {total_duration:.2f}s'
			)

			return {
				'status': 'completed',
				'job_id': job_id,
				'chunks_processed': len(chunks),
				'duration_seconds': round(total_duration, 2),
			}

		except Exception as e:
			logger.error(f'[{job_id}] Pipeline failed: {e}', exc_info=True)
			raise  # Re-raise to let the API/Worker handle the failure state

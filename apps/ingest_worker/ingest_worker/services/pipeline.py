import logging
import time
from typing import Any, BinaryIO

from fastapi.concurrency import run_in_threadpool
from ingest_worker.extractors.chunker import SectionChunker
from ingest_worker.extractors.pdf_parser import PdfParser
from ingest_worker.intelligence.embedding import EmbeddingService
from ingest_worker.intelligence.vector_store import VectorStore
from ingest_worker.services.deduplicator import Deduplicator
from ingest_worker.services.definition_extractor import DefinitionExtractor
from ingest_worker.services.obligation_extractor import ObligationExtractor

logger = logging.getLogger(__name__)


class IngestionPipeline:
	"""
	Orchestrates the conversion of raw documents into indexed vectors
	AND machine-enforceable obligations.

	Flow:
	1. Parse (OCR) -> Elements
	2. Chunk -> Semantic Blocks
	3. Embed -> Vectors
	4. Index -> Qdrant (RAG Memory)
	5. Pass 1 -> Extract Definitions (Glossary)
	6. Pass 2 -> Extract Constraints (Raw Rules)
	7. Pass 3 -> Deduplicate & Merge (Final Policy)
	"""

	def __init__(self):
		# Phase 1: Physical Extraction
		self.parser = PdfParser()
		self.chunker = SectionChunker(max_tokens=800)

		# Phase 2: Vector Memory
		self.embedder = EmbeddingService()
		self.vector_store = VectorStore()

		# Phase 3: Legal Reasoning (The "Brain")
		self.def_extractor = DefinitionExtractor()
		self.rule_extractor = ObligationExtractor()
		self.deduplicator = Deduplicator()

	async def initialize(self):
		"""
		Lifecycle hook: Run on app startup.
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
		"""
		start_time = time.time()
		logger.info(f'[{job_id}] Starting ingestion for: {filename}')

		try:
			# ==================================================================
			# STEP 1: PARSING (CPU)
			# ==================================================================
			parse_start = time.time()
			elements = await run_in_threadpool(self.parser.parse, file, filename)

			if not elements:
				logger.warning(f'[{job_id}] No text extracted from file.')
				return {'status': 'empty_file', 'chunks': 0}

			logger.info(f'[{job_id}] Parsed {len(elements)} elements in {time.time() - parse_start:.2f}s')

			# ==================================================================
			# STEP 2: CHUNKING (CPU)
			# ==================================================================
			chunks = self.chunker.chunk(elements, filename)
			logger.info(f'[{job_id}] Generated {len(chunks)} semantic chunks')

			if not chunks:
				return {'status': 'no_chunks_generated', 'chunks': 0}

			# ==================================================================
			# STEP 3: EMBEDDING (GPU/API)
			# ==================================================================
			embed_start = time.time()
			texts = [c.content for c in chunks]
			vectors = await self.embedder.embed_documents(texts)
			logger.info(f'[{job_id}] Generated embeddings in {time.time() - embed_start:.2f}s')

			# ==================================================================
			# STEP 4: INDEXING (DB IO)
			# ==================================================================
			# We persist vectors so we can use RAG later or debug the LLM's view
			await self.vector_store.upsert_chunks(
				job_id=job_id,
				project_id=project_id,
				chunks=chunks,
				vectors=vectors,
			)

			# ==================================================================
			# STEP 5: PASS 1 - DEFINITIONS (LLM)
			# ==================================================================
			# Build the glossary to ground the subsequent rule extraction
			def_start = time.time()
			context = await self.def_extractor.extract(chunks)
			logger.info(f'[{job_id}] Definitions extracted in {time.time() - def_start:.2f}s')

			# ==================================================================
			# STEP 6: PASS 2 - CONSTRAINTS (LLM Parallel)
			# ==================================================================
			rule_start = time.time()
			raw_constraints = await self.rule_extractor.extract_all(chunks, context)
			logger.info(f'[{job_id}] Constraints extracted in {time.time() - rule_start:.2f}s')

			# ==================================================================
			# STEP 7: PASS 3 - DEDUPLICATION (CPU)
			# ==================================================================
			# Flatten redundancy and convert to final Schema
			final_obligations = self.deduplicator.merge(raw_constraints, filename=filename, project_id=project_id)

			total_duration = time.time() - start_time
			logger.info(
				f'[{job_id}] Pipeline Complete. '
				f'Final Result: {len(final_obligations)} obligations. '
				f'Total Time: {total_duration:.2f}s'
			)

			# Return stats AND the actual objects
			# The API handler (main.py) will map this to the response model.
			return {
				'status': 'completed',
				'job_id': job_id,
				'duration_seconds': round(total_duration, 2),
				'chunks_processed': len(chunks),
				'definitions_found': len(context.definitions),
				'raw_constraints_found': len(raw_constraints),
				'final_obligations_count': len(final_obligations),
				# Return serialized obligations so they can be sent to Control Plane
				# or returned to the user immediately.
				'obligations': [ob.model_dump(mode='json') for ob in final_obligations],
			}

		except Exception as e:
			logger.error(f'[{job_id}] Pipeline failed: {e}', exc_info=True)
			raise

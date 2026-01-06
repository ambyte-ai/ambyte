import asyncio
import logging
import re

from ingest_worker.intelligence.llm_client import LlmClient
from ingest_worker.intelligence.regulation_search import RegulationSearch
from ingest_worker.schemas.ingest import (
	ContractContext,
	DocumentChunk,
	ExtractedConstraint,
)

logger = logging.getLogger(__name__)


class ObligationExtractor:
	"""
	PASS 2: The Core Reasoning Engine.

	Iterates through document chunks, injects the 'Dictionary' (Context),
	and extracts structured constraints.
	"""

	def __init__(self, concurrency_limit: int = 5):
		self.llm = LlmClient()
		self.reg_search = RegulationSearch()
		# Semaphore to prevent hitting OpenAI rate limits
		self.semaphore = asyncio.Semaphore(concurrency_limit)

	async def extract_all(self, chunks: list[DocumentChunk], context: ContractContext) -> list[ExtractedConstraint]:
		"""
		Orchestrates parallel extraction across all chunks.
		"""
		logger.info(f'Starting Pass 2: Extracting constraints from {len(chunks)} chunks...')

		tasks = []
		for chunk in chunks:
			# Skip chunks that are likely too short or just headers/footers
			# (Token count check is a good heuristic)
			if chunk.token_count < 20:
				continue

			tasks.append(self._process_chunk(chunk, context))

		# Run parallel
		results = await asyncio.gather(*tasks, return_exceptions=True)

		# Flatten and filter failures
		valid_constraints = []
		for res in results:
			if isinstance(res, list):
				valid_constraints.extend(res)
			elif isinstance(res, Exception):
				logger.warning(f'Chunk extraction failed: {res}')

		logger.info(f'Pass 2 Complete. Extracted {len(valid_constraints)} raw constraints.')
		return valid_constraints

	async def _process_chunk(self, chunk: DocumentChunk, context: ContractContext) -> list[ExtractedConstraint]:
		"""
		Process a single chunk with hallucinations checks.
		"""
		async with self.semaphore:
			try:
				# 1. Expand Context with RAG (Regulatory Knowledge)
				# We search for canonical rules that match this text chunk
				reg_matches = await self.reg_search.find_applicable_rules(chunk.content)
				reg_context_str = self.reg_search.format_matches_for_prompt(reg_matches)

				# 2. LLM Call
				result = await self.llm.extract_constraints(chunk.content, context, regulatory_context=reg_context_str)

				valid_items = []

				# 2. Validation / Hallucination Check
				for item in result.constraints:
					if self._verify_provenance(item.quote, chunk.content):
						# Attach metadata that the LLM doesn't know about
						# (e.g. filename, page number are known by the wrapper, not the prompt)
						# We embed this into the rationale or source context for the next step.
						item.source_metadata = {
							'chunk_id': str(chunk.chunk_id),
							'page_number': chunk.metadata.page_number,
							'section_hierarchy': chunk.metadata.section_hierarchy,
						}
						valid_items.append(item)
					else:
						logger.warning(
							f'Hallucination detected! Quote not found in text.\n'
							f"Quote: '{item.quote}'\n"
							f'Chunk ID: {chunk.chunk_id}'
						)

				return valid_items

			except Exception as e:
				# Log but re-raise so gather captures it
				logger.error(f'Error processing chunk {chunk.chunk_id}: {e}')
				raise e

	def _verify_provenance(self, quote: str, full_text: str) -> bool:
		"""
		Verifies that the extracted quote actually exists in the source text.
		Uses normalization to handle whitespace/formatting artifacts.
		"""
		if not quote:
			return False

		# 1. Normalize both strings
		# Remove all whitespace, newlines, and convert to lower case
		def normalize(s: str) -> str:
			# Remove whitespace
			s = re.sub(r'\s+', '', s).lower()
			# Remove surrounding quotes that the LLM might have hallucinated
			s = s.strip('"').strip("'")
			return s

		clean_quote = normalize(quote)
		clean_text = normalize(full_text)

		# 2. Check inclusion
		# Use a threshold for very short quotes to avoid false positives?
		# For now, strict inclusion on normalized text is robust enough. # TODO
		return clean_quote in clean_text

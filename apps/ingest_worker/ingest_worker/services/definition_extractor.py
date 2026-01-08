import logging
import re

from ingest_worker.intelligence.llm_client import LlmClient
from ingest_worker.schemas.ingest import ContractContext, DocumentChunk

logger = logging.getLogger(__name__)


class DefinitionExtractor:
	"""
	PASS 1: Scans the document to build a 'Dictionary' of defined terms.

	Strategy:
	Instead of processing every chunk (expensive), we use heuristics to find
	the 'Definitions' section (usually early in the doc) and process that deeply.
	"""

	def __init__(self):
		self.llm = LlmClient()
		self._quoted_term_pattern = re.compile(r'["“]([A-Z][a-zA-Z0-9\s-]+)["”]')

	async def extract(self, chunks: list[DocumentChunk]) -> ContractContext:
		"""
		Builds the ContractContext by finding and processing definition sections.
		"""
		logger.info('Starting Pass 1: Definition Extraction')

		# 1. Heuristic Filtering
		# We look for chunks that likely contain definitions to save tokens.
		# - Title contains "Definitions"
		# - First 5 pages (contracts usually define terms early)
		candidate_chunks = self._identify_definition_candidates(chunks)

		# 2. Fallback: Density Scan (if explicit headers missing)
		if not candidate_chunks:
			logger.info("No explicit 'Definitions' header found. Attempting fallback (Page 1-3 density scan).")
			candidate_chunks = self._scan_first_pages_fallback(chunks)

		if not candidate_chunks:
			logger.warning('No definitions found after fallback. Proceeding with empty context.')
			return ContractContext()

		# 3. Parallel Extraction
		# Optimization: Merge contiguous text into larger blocks to give LLM more context
		merged_text = '\n\n'.join([c.content for c in candidate_chunks])

		# If the definitions section is huge (>10k tokens), we might need to split.
		# For now, we assume it fits in GPT-5.2 context (128k).

		try:
			context = await self.llm.extract_definitions(merged_text)
			logger.info(f'Pass 1 Complete. Found {len(context.definitions)} defined terms.')
			return context
		except Exception as e:
			logger.error(f'Pass 1 Failed: {e}')
			# Fail open: Return empty context rather than crashing the job
			return ContractContext()

	def _identify_definition_candidates(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
		"""
		Selects chunks that look like they belong to the 'Definitions' article.
		"""
		candidates = []
		is_in_definitions_section = False

		# Sort by page/sequence to read linearly
		# Assuming chunks list corresponds to document order

		for chunk in chunks:
			text_lower = chunk.content.lower()[:200]  # Check start of chunk
			hierarchy_str = ' '.join(chunk.metadata.section_hierarchy).lower()

			# Detect Start of Section
			if 'definition' in text_lower or 'definition' in hierarchy_str:
				is_in_definitions_section = True
				candidates.append(chunk)
				continue

			# Heuristic: If we hit another major Article (e.g. "2. Term", "3. Services"), stop.
			if is_in_definitions_section:
				# If we hit a new Title that DOESN'T look like a definition sub-header
				if not self._is_definition_subheader(chunk.content):
					is_in_definitions_section = False
					continue

				candidates.append(chunk)

		return candidates

	def _scan_first_pages_fallback(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
		"""
		Fallback strategy: Scans the first 3 pages for chunks containing
		a high density of quoted terms (e.g. "Customer Data").
		"""
		candidates = []

		early_chunks = [c for c in chunks if c.metadata.page_number <= 3]

		for chunk in early_chunks:
			matches = self._quoted_term_pattern.findall(chunk.content)

			# Threshold: If a chunk has >= 2 quoted terms, it's likely part of a definition list
			# or a Preamble defining the parties ("Customer" and "Provider").
			if len(matches) >= 2:
				candidates.append(chunk)

			elif 'shall mean' in chunk.content or 'means any' in chunk.content:
				candidates.append(chunk)

		return candidates

	def _is_definition_subheader(self, text: str) -> bool:
		"""
		Returns True if the title looks like a defined term entry.
		e.g., '"Customer Data"' or '1.1 Affiliate'
		"""
		# Checks for short titles often found in definition lists
		if len(text.split()) < 5:
			return True
		return False

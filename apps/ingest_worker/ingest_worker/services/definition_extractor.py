import logging

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

		if not candidate_chunks:
			logger.warning("No explicit 'Definitions' section found. Proceeding with empty context.")
			return ContractContext()

		# 2. Parallel Extraction
		# In a real heavy-load system, we might limit concurrency here.
		# For now, we process candidates sequentially or in simple loop to build the unified list.
		# (Definitions usually span contiguous chunks, so we just concat them). # TODO

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
			is_title = chunk.metadata.element_type == 'Title'

			# Detect Start of Section
			if is_title and ('definition' in text_lower or 'interpretation' in text_lower):
				is_in_definitions_section = True
				candidates.append(chunk)
				continue

			# Heuristic: If we hit another major Article (e.g. "2. Term", "3. Services"), stop.
			if is_in_definitions_section:
				# If we hit a new Title that DOESN'T look like a definition sub-header
				if is_title and not self._is_definition_subheader(chunk.content):
					is_in_definitions_section = False
					continue

				candidates.append(chunk)

		# Fallback: If we didn't find a clear section, check the first 3 pages
		# for high density of quoted terms?
		# For MVP, if heuristic fails, we just return nothing to avoid noise. # TODO

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

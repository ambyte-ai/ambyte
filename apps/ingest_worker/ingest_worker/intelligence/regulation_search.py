import logging
from typing import Any

from ambyte_schemas.models.ontology import TechnicalEnforcement
from ingest_worker.intelligence.embedding import EmbeddingService
from ingest_worker.intelligence.vector_store import VectorStore

logger = logging.getLogger(__name__)


class RegulationSearch:
	"""
	Retrieval Service for the Regulatory Knowledge Graph.

	Used by the Obligation Extractor to find canonical definitions matching
	unstructured contract text.
	"""

	def __init__(self):
		self.embedder = EmbeddingService()
		self.vector_store = VectorStore()

	async def find_applicable_rules(
		self,
		text_chunk: str,
		jurisdiction: str | None = None,
		threshold: float = 0.78,
		limit: int = 3,
	) -> list[dict[str, Any]]:
		"""
		Semantic Search against the 'ambyte_regulations' collection.

		Args:
		    text_chunk: The raw text from the document being processed.
		    jurisdiction: Optional filter (e.g. 'EU') to narrow search scope.
		    threshold: Minimum similarity score (0.0 to 1.0).
		               Defaults to 0.78 (high precision) to avoid noise.
		    limit: Max number of matches to return.

		Returns:
		    A list of dictionaries representing the Matched Rule Context.
		    Each item contains:
		    - source: "GDPR Art 17"
		    - description: "Right to Erasure..."
		    - required_config: The TechnicalEnforcement dict.
		"""  # noqa: E101
		if not text_chunk or len(text_chunk.strip()) < 10:
			return []

		try:
			# 1. Generate Embedding for the query (text chunk)
			# We use 'query' input type for VoyageAI optimization
			query_vector = await self.embedder.embed_query(text_chunk)

			# 2. Query Qdrant
			results = await self.vector_store.search_regulations(
				query_vector=query_vector,
				limit=limit,
				jurisdiction=jurisdiction,
				score_threshold=threshold,
			)

			# 3. Format Results for LLM Injection
			matches = []
			for point in results:
				payload = point.payload
				if not payload:
					continue

				# Parse the stored JSON back into the strict model for validation
				# (Optional safety check, ensures we only pass valid schemas)
				try:
					tech_enforcement = TechnicalEnforcement.model_validate(payload['technical_enforcement'])

					# Convert back to clean JSON for the prompt
					config_json = tech_enforcement.model_dump(mode='json', exclude_none=True, exclude_defaults=True)

					match_context = {
						'regulation': payload['regulation_id'],
						'reference': payload['source_reference'],
						'title': payload['title'],
						'description': payload['description'],
						'required_config': config_json,
						'score': point.score,
					}
					matches.append(match_context)

				except Exception as e:
					logger.warning(f'Skipping malformed regulation payload: {e}')
					continue

			if matches:
				logger.debug(f'Found {len(matches)} regulatory matches for chunk.')

			return matches

		except Exception as e:
			logger.error(f'Regulation search failed: {e}')
			# Fail open: Return empty list so extraction can proceed without context
			return []

	def format_matches_for_prompt(self, matches: list[dict[str, Any]]) -> str:
		"""
		Helper to convert the structured matches into a string block
		suitable for injection into the System Prompt.
		"""
		if not matches:
			return ''

		blocks = []
		for m in matches:
			block = f"""
- MATCHED REGULATION: {m['regulation']} ({m['reference']}) - "{m['title']}"
  DESCRIPTION: {m['description']}
  REQUIRED TECHNICAL CONFIGURATION:
  {m['required_config']}
"""
			blocks.append(block)

		return '\n'.join(blocks)

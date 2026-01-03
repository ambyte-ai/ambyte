import logging
from typing import Literal, cast

from ingest_worker.config import settings
from tenacity import (
	retry,
	retry_if_exception_type,
	stop_after_attempt,
	wait_exponential,
)
from voyageai.client_async import AsyncClient

logger = logging.getLogger(__name__)


class EmbeddingService:
	"""
	Wrapper around Voyage AI for generating domain-specific legal embeddings.
	Handles batching, async execution, and retries.
	"""

	def __init__(self):
		# Initialize the Async client.
		# Voyage's AsyncClient creates ephemeral aiohttp sessions per request by default.
		self.client = AsyncClient(api_key=settings.voyage_api_key_val)

		self.model = settings.EMBEDDING_MODEL
		self.batch_size = settings.EMBEDDING_BATCH_SIZE

	async def embed_documents(self, texts: list[str]) -> list[list[float]]:
		"""
		Generates embeddings for a list of document chunks (Corpus).
		Automatically splits the input into manageable batches to respect API limits.

		Args:
			texts: List of text strings to embed.

		Returns:
			A list of vector embeddings (list of floats) corresponding to the inputs.
		"""  # noqa: E101
		return await self._process_batches(texts, input_type='document')

	async def embed_query(self, text: str) -> list[float]:
		"""
		Generates an embedding for a search query.
		Voyage optimizes retrieval by distinguishing between 'document' and 'query'.

		Args:
			text: The search query string.

		Returns:
			A single vector embedding.
		"""  # noqa: E101
		# Wrap single string in list, extract first result
		results = await self._process_batches([text], input_type='query')
		return results[0]

	async def _process_batches(self, texts: list[str], input_type: Literal['document', 'query']) -> list[list[float]]:
		"""
		Internal orchestrator to split a large list of texts into batches
		and aggregate the results.
		"""
		total_texts = len(texts)
		if total_texts == 0:
			return []

		all_embeddings: list[list[float]] = []

		logger.debug(f'Starting embedding for {total_texts} items. Model: {self.model}, Batch Size: {self.batch_size}')

		# Iterate with stride
		for i in range(0, total_texts, self.batch_size):
			batch = texts[i : i + self.batch_size]
			batch_idx = i // self.batch_size + 1
			total_batches = (total_texts + self.batch_size - 1) // self.batch_size

			try:
				# Call the retriable raw API method
				logger.debug(f'Embedding batch {batch_idx}/{total_batches} ({len(batch)} items)')
				batch_vectors = await self._embed_batch_raw(batch, input_type)
				all_embeddings.extend(batch_vectors)
			except Exception as e:
				logger.error(f'Failed to embed batch {batch_idx}: {e}')
				# We raise here because missing embeddings corrupts the document index.
				# In a robust queue system, this would trigger a job retry. # TODO
				raise

		return all_embeddings

	@retry(
		retry=retry_if_exception_type(Exception),  # Voyage client might raise generic exceptions on network err
		stop=stop_after_attempt(5),
		wait=wait_exponential(multiplier=1, min=2, max=60),
		reraise=True,
	)
	async def _embed_batch_raw(self, batch: list[str], input_type: Literal['document', 'query']) -> list[list[float]]:
		"""
		Low-level API call with Retry logic.
		"""
		# Voyage AI specific: input_type helps the model optimize the vector space
		# for asymmetric retrieval (short query vs long document).
		response = await self.client.embed(
			texts=batch,
			model=self.model,
			input_type=input_type,
			truncation=True,  # Safety net if chunker missed a spot
		)

		return cast(list[list[float]], response.embeddings)

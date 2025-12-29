import logging

from ingest_worker.config import settings
from ingest_worker.schemas.ingest import DocumentChunk
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)


class VectorStore:
	"""
	Manages persistence and retrieval of embedding vectors in Qdrant.
	Stores full text content in the payload to enable retrieval (RAG).
	"""

	def __init__(self):
		# Initialize Async Client
		self.client = AsyncQdrantClient(
			url=settings.QDRANT_URL,
			api_key=settings.qdrant_api_key_val,
		)
		self.collection_name = settings.QDRANT_COLLECTION_NAME

	async def ensure_collection(self):
		"""
		Idempotent setup: Creates the collection if it doesn't exist.
		Configures it for the specific embedding model dimensions.
		"""
		try:
			exists = await self.client.collection_exists(self.collection_name)
			if not exists:
				logger.info(
					f"Creating Qdrant collection '{self.collection_name}' (dim={settings.EMBEDDING_DIM}, metric=Cosine)"
				)
				await self.client.create_collection(
					collection_name=self.collection_name,
					vectors_config=models.VectorParams(
						size=settings.EMBEDDING_DIM,
						distance=models.Distance.COSINE,
					),
				)

				# Create Payload Indexes for fast filtering
				# We almost always filter by job_id (specific document) or project_id
				await self._create_index('job_id', 'keyword')
				await self._create_index('metadata.filename', 'keyword')
				await self._create_index('metadata.page_number', 'integer')

		except Exception as e:
			logger.error(f'Failed to initialize Qdrant collection: {e}')
			raise

	async def _create_index(self, field_name: str, schema_type: str):
		"""Helper to create payload indexes safely."""
		try:
			await self.client.create_payload_index(
				collection_name=self.collection_name,
				field_name=field_name,
				field_schema=schema_type,
			)
		except UnexpectedResponse:
			# Often means index already exists or is being created
			pass

	async def upsert_chunks(
		self,
		job_id: str,
		project_id: str | None,
		chunks: list[DocumentChunk],
		vectors: list[list[float]],
	) -> int:
		"""
		Persist document chunks and their vectors.

		Args:
		    job_id: The unique ID of the ingestion job (links chunks to a specific upload).
		    project_id: Optional grouping for multi-tenancy.
		    chunks: The semantic text blocks.
		    vectors: The embeddings corresponding to the chunks (1:1 mapping).

		Returns:
		    Count of points upserted.
		"""  # noqa: E101
		if len(chunks) != len(vectors):
			raise ValueError(f'Mismatch: {len(chunks)} chunks vs {len(vectors)} vectors.')

		points = []
		for chunk, vector in zip(chunks, vectors, strict=True):
			# Flatten metadata for easier querying, but keep structure clean
			payload = {
				'content': chunk.content,
				'job_id': job_id,
				'project_id': project_id,
				# Store the Pydantic metadata model as a dict
				'metadata': chunk.metadata.model_dump(mode='json'),
				'token_count': chunk.token_count,
			}

			points.append(
				models.PointStruct(
					id=str(chunk.chunk_id),  # Qdrant supports UUID strings
					vector=vector,
					payload=payload,
				)
			)

		# Upsert in batch
		# Qdrant handles large batches well, but extremely large docs (>10k chunks)
		# might need chunking here too. For now, we assume <2k chunks per doc.
		if points:
			await self.client.upsert(
				collection_name=self.collection_name,
				points=points,
			)
			logger.info(f'Upserted {len(points)} vectors to Qdrant for job {job_id}')

		return len(points)

	async def search(
		self,
		query_vector: list[float],
		limit: int = 5,
		job_id: str | None = None,
		project_id: str | None = None,
		score_threshold: float = 0.4,
	) -> list[models.ScoredPoint]:
		"""
		Semantic retrieval.

		Args:
		    query_vector: The embedding of the search query/prompt.
		    limit: Max results.
		    job_id: If set, restrict search to a specific document upload.
		    project_id: If set, restrict search to a specific workspace.
		    score_threshold: Minimum similarity to return (cutoff noise).

		Returns:
		    List of ScoredPoint (id, score, payload, etc.)
		"""  # noqa: E101
		# Build Filter
		must_conditions = []
		if job_id:
			must_conditions.append(models.FieldCondition(key='job_id', match=models.MatchValue(value=job_id)))
		if project_id:
			must_conditions.append(models.FieldCondition(key='project_id', match=models.MatchValue(value=project_id)))

		filter_obj = models.Filter(must=must_conditions) if must_conditions else None

		results = await self.client.query_points(
			collection_name=self.collection_name,
			query=query_vector,
			query_filter=filter_obj,
			limit=limit,
			score_threshold=score_threshold,
			with_payload=True,  # We need the text content back!
		)

		return results.points

	async def delete_job(self, job_id: str):
		"""Cleanup logic: Remove all vectors associated with a job."""
		await self.client.delete(
			collection_name=self.collection_name,
			points_selector=models.FilterSelector(
				filter=models.Filter(must=[models.FieldCondition(key='job_id', match=models.MatchValue(value=job_id))])
			),
		)

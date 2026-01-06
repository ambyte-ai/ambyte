import logging
import uuid

from ambyte_schemas.models.ontology import RegulationDefinition
from ingest_worker.config import settings
from ingest_worker.schemas.ingest import DocumentChunk
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

REGULATION_COLLECTION_NAME = 'ambyte_regulations'


class VectorStore:
	"""
	Manages persistence and retrieval of embedding vectors in Qdrant.
	Handles two distinct collections:
	1. 'ambyte_legal_docs': Uploaded contracts/documents (Ephemeral or Project-scoped).
	2. 'ambyte_regulations': The canonical Knowledge Graph (System-scoped).
	"""

	def __init__(self):
		# Initialize Async Client
		self.client = AsyncQdrantClient(
			url=settings.QDRANT_URL,
			api_key=settings.qdrant_api_key_val,
		)
		self.doc_colletion = settings.QDRANT_COLLECTION_NAME
		self.reg_collection = REGULATION_COLLECTION_NAME

	async def ensure_collections(self):
		"""
		Idempotent setup: Creates both document and regulation collections if missing.
		"""
		await self._ensure_document_collection()
		await self._ensure_regulation_collection()

	async def _ensure_document_collection(self):
		"""
		Idempotent setup: Creates the document collection if it doesn't exist.
		Configures it for the specific embedding model dimensions.
		"""
		try:
			exists = await self.client.collection_exists(self.doc_colletion)
			if not exists:
				logger.info(
					f"Creating Qdrant collection '{self.doc_colletion}' (dim={settings.EMBEDDING_DIM}, metric=Cosine)"
				)
				await self.client.create_collection(
					collection_name=self.doc_colletion,
					vectors_config=models.VectorParams(
						size=settings.EMBEDDING_DIM,
						distance=models.Distance.COSINE,
					),
				)

				# Create Payload Indexes for fast filtering
				# We almost always filter by job_id (specific document) or project_id
				await self._create_index(self.doc_colletion, 'job_id', 'keyword')
				await self._create_index(self.doc_colletion, 'project_id', 'keyword')
				await self._create_index(self.doc_colletion, 'metadata.filename', 'keyword')
				await self._create_index(self.doc_colletion, 'metadata.page_number', 'integer')

		except Exception as e:
			logger.error(f'Failed to initialize Qdrant collection: {e}')
			raise

	async def _ensure_regulation_collection(self):
		"""
		Sets up the Knowledge Graph collection.
		"""
		try:
			if not await self.client.collection_exists(self.reg_collection):
				logger.info(f"Creating Regulation collection '{self.reg_collection}'...")
				await self.client.create_collection(
					collection_name=self.reg_collection,
					vectors_config=models.VectorParams(
						size=settings.EMBEDDING_DIM,
						distance=models.Distance.COSINE,
					),
				)
				# Payload Indexes for Regulations
				await self._create_index(self.reg_collection, 'regulation_id', 'keyword')
				await self._create_index(self.reg_collection, 'jurisdiction', 'keyword')
				await self._create_index(self.reg_collection, 'classification_type', 'keyword')
		except Exception as e:
			logger.error(f'Failed to init regulation collection: {e}')
			raise

	async def _create_index(self, collection: str, field_name: str, schema_type: str):
		"""Helper to create payload indexes safely."""
		try:
			await self.client.create_payload_index(
				collection_name=collection,
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
				collection_name=self.doc_colletion,
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
			collection_name=self.doc_colletion,
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
			collection_name=self.doc_colletion,
			points_selector=models.FilterSelector(
				filter=models.Filter(must=[models.FieldCondition(key='job_id', match=models.MatchValue(value=job_id))])
			),
		)

	async def upsert_regulations(self, regulation: RegulationDefinition, vectors: list[list[float]]) -> int:
		"""
		Persist canonical regulations into the Knowledge Graph.

		The Payload includes the 'TechnicalEnforcement' object serialized to JSON.
		This allows retrieval operations to get the exact configuration immediately
		without a secondary database lookup.
		"""
		rules = regulation.mappings
		if len(rules) != len(vectors):
			raise ValueError(f'Mismatch: {len(rules)} rules vs {len(vectors)} vectors.')

		points = []
		for rule, vector in zip(rules, vectors, strict=True):
			# Deterministic ID ensures we update existing rules rather than duplicate
			# UUID5(NAMESPACE_DNS, "EU-GDPR-2016/679::Art. 5(1)(a)")
			unique_str = f'{regulation.regulation_id}::{rule.source_reference}'
			point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_str))

			payload = {
				'regulation_id': regulation.regulation_id,
				'jurisdiction': regulation.jurisdiction,
				'source_reference': rule.source_reference,
				'title': rule.title,
				'description': rule.description,
				# CRITICAL: Store the strict technical configuration
				'technical_enforcement': rule.technical_enforcement.model_dump(mode='json'),
				# Metadata for filtering
				'classification_type': rule.classification.type,
				'classification_severity': rule.classification.severity,
			}

			points.append(
				models.PointStruct(
					id=point_id,
					vector=vector,
					payload=payload,
				)
			)

		if points:
			await self.client.upsert(collection_name=self.reg_collection, points=points)
			logger.info(f'Upserted {len(points)} regulatory rules to {self.reg_collection}')

		return len(points)

	async def search_regulations(
		self,
		query_vector: list[float],
		limit: int = 3,
		jurisdiction: str | None = None,
		score_threshold: float = 0.75,  # High threshold to avoid noise
	) -> list[models.ScoredPoint]:
		"""
		Finds regulatory clauses matching a text embedding.
		Used by the Extraction Service to ground the LLM.
		"""
		must_conditions = []
		if jurisdiction:
			must_conditions.append(
				models.FieldCondition(key='jurisdiction', match=models.MatchValue(value=jurisdiction))
			)

		filter_obj = models.Filter(must=must_conditions) if must_conditions else None

		results = await self.client.query_points(
			collection_name=self.reg_collection,
			query=query_vector,
			query_filter=filter_obj,
			limit=limit,
			score_threshold=score_threshold,
			with_payload=True,
		)
		return results.points

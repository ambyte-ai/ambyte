import asyncio
import hashlib
import logging
from pathlib import Path

import yaml
from ambyte_schemas.models.ontology import RegulationDefinition
from ingest_worker.intelligence.embedding import EmbeddingService
from ingest_worker.intelligence.vector_store import VectorStore
from ingest_worker.services.job_store import job_store

logger = logging.getLogger(__name__)

# Constants
ONTOLOGY_PATH_LOCAL = Path('../../schemas/ontology')  # Relative from apps/ingest_worker
ONTOLOGY_PATH_DOCKER = Path('/app/schemas/ontology')  # Standard Docker layout


class RegulationIndexer:
	"""
	Manages the lifecycle of the Regulatory Knowledge Graph.

	Responsibilities:
	1. Scans the 'schemas/ontology' directory for YAML definitions.
	2. Checks Redis to see if the file has changed since last run (Hash check).
	3. If changed:
	   - Parses the YAML into Pydantic models.
	   - Generates embeddings for every rule using VoyageAI.
	   - Upserts the rules + technical payloads into the 'ambyte_regulations' Qdrant collection.
	"""  # noqa: E101

	def __init__(self):
		self.embedder = EmbeddingService()
		self.vector_store = VectorStore()
		self._redis = None

	async def initialize(self):
		"""
		Setup required connections and ensure the Qdrant collection exists.
		"""
		# Reuse the Redis connection from job_store for hash tracking
		if not job_store._redis:
			await job_store.initialize()
		self._redis = job_store._redis

		await self.vector_store.ensure_collections()

	async def index_all(self):
		"""
		Main Entrypoint: Scans all ontology files and processes changes.
		"""
		ontology_dir = self._resolve_ontology_path()
		if not ontology_dir.exists():
			logger.warning(f'Ontology directory not found at {ontology_dir}. Skipping regulation indexing.')
			return

		logger.info(f'Scanning for regulatory mappings in {ontology_dir}...')

		files = [f for f in ontology_dir.glob('*_mappings.yaml') if f.name != 'snowflake_mappings.yaml']
		if not files:
			logger.info('No mapping files found.')
			return

		for file_path in files:
			try:
				await self._process_file(file_path)
			except Exception as e:
				logger.error(f'Failed to index regulation file {file_path.name}: {e}', exc_info=True)

	async def _process_file(self, file_path: Path):
		"""
		Handles change detection and indexing for a single YAML file.
		"""
		# 1. Calculate File Hash
		content = await asyncio.to_thread(file_path.read_bytes)

		current_hash = hashlib.sha256(content).hexdigest()
		cache_key = f'ambyte:ontology:hash:{file_path.name}'

		# 2. Check Cache
		if self._redis:
			stored_hash = await self._redis.get(cache_key)
			if stored_hash == current_hash:
				logger.debug(f'Skipping {file_path.name} (Unchanged)')
				return

		logger.info(f'Detected changes in {file_path.name}. Re-indexing...')

		# 3. Parse YAML
		try:
			data = yaml.safe_load(content.decode('utf-8'))
			regulation = RegulationDefinition.model_validate(data)
		except Exception as e:
			logger.error(f'Schema validation failed for {file_path.name}: {e}')
			return

		# 4. Prepare Embeddings
		rules_to_index = regulation.mappings
		if not rules_to_index:
			return

		# Extract text for vectorization: "Art 5(1) Title: Description..."
		texts = [rule.embedding_text for rule in rules_to_index]

		logger.info(f'Generating embeddings for {len(texts)} rules in {regulation.regulation_id}...')
		vectors = await self.embedder.embed_documents(texts)

		# 5. Persist to Qdrant via VectorStore
		await self.vector_store.upsert_regulations(regulation, vectors)

		# 7. Update Cache
		if self._redis:
			await self._redis.set(cache_key, current_hash)

	def _resolve_ontology_path(self) -> Path:
		"""
		Determines the absolute path to the schemas folder based on environment.
		"""
		if ONTOLOGY_PATH_DOCKER.exists():
			return ONTOLOGY_PATH_DOCKER

		# Fallback for local development relative to this file
		# This file is in apps/ingest_worker/ingest_worker/services/
		# We need to go up 4 levels: services -> ingest_worker -> apps -> root
		current_file = Path(__file__).resolve()
		repo_root = current_file.parents[4]
		return repo_root / 'schemas' / 'ontology'

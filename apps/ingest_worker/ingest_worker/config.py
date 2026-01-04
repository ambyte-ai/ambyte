from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
	LOCAL = 'local'
	STAGING = 'staging'
	PRODUCTION = 'production'


class Settings(BaseSettings):
	"""
	Global configuration for the Ingest Worker.
	Loads from environment variables (e.g., AMBYTE_INGEST_QDRANT_URL) or .env file.
	"""

	model_config = SettingsConfigDict(
		env_prefix='AMBYTE_INGEST_',  # Namespace to avoid collisions
		env_file='.env',
		env_file_encoding='utf-8',
		extra='ignore',
		case_sensitive=False,
	)

	# ==========================================================================
	# Service Metadata
	# ==========================================================================
	ENV: Environment = Field(default=Environment.LOCAL)
	SERVICE_NAME: str = 'ingest-worker'
	LOG_LEVEL: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'

	# ==========================================================================
	# Vector Database (Qdrant)
	# ==========================================================================
	QDRANT_URL: str = Field(
		default='http://qdrant:6333',
		description='Internal Docker URL or Cloud Endpoint.',
	)
	QDRANT_API_KEY: SecretStr | None = Field(
		default=None,
		description='Required for Qdrant Cloud or protected instances.',
	)
	# The name of the collection where we store legal document chunks
	QDRANT_COLLECTION_NAME: str = 'ambyte_legal_docs'

	# ==========================================================================
	# Job Store (Redis)
	# ==========================================================================
	REDIS_JOB_STORE_URL: str = Field(
		default='redis://redis:6379/0',
		description='Redis URL for job state persistence. DB 0 reserved for jobs.',
	)

	# ==========================================================================
	# Blob Storage (S3 / MinIO)
	# ==========================================================================
	S3_ENDPOINT_URL: str = Field(
		default='http://minio:9000',
		description='URL for S3-compatible storage (e.g. MinIO, AWS S3)',
	)
	S3_BUCKET_NAME: str = Field(
		default='ambyte-raw',
		description='Bucket for storing raw uploaded documents.',
	)
	S3_REGION: str = Field(
		default='us-east-1',
		description='Region for S3-compatible storage (e.g. MinIO, AWS S3)',
	)

	# ==========================================================================
	# Embeddings (Voyage AI)
	# ==========================================================================
	# We use Voyage AI for domain-specific legal embeddings (SOTA for law).
	VOYAGE_API_KEY: SecretStr = Field(
		...,
		description='API Key for Voyage AI. Critical for vector generation.',
	)
	# voyage-law-2 is optimized for legal retrieval (contracts, regulations).
	EMBEDDING_MODEL: str = 'voyage-law-2'
	# voyage-law-2 output dimension is 1024
	EMBEDDING_DIM: int = 1024
	# Max batch size to send to Voyage API to avoid rate limits/timeouts
	EMBEDDING_BATCH_SIZE: int = 128

	# ==========================================================================
	# Extraction (OpenAI / LLM) - Phase 3
	# ==========================================================================
	# Still used for the generative extraction step
	OPENAI_API_KEY: SecretStr = Field(
		...,
		description='API Key for OpenAI (GPT-5.2) used in extraction phase.',
	)
	EXTRACTION_MODEL: str = 'gpt-5.2'

	@computed_field
	@property
	def is_local(self) -> bool:
		return self.ENV == Environment.LOCAL

	@property
	def qdrant_api_key_val(self) -> str | None:
		return self.QDRANT_API_KEY.get_secret_value() if self.QDRANT_API_KEY else None

	@property
	def voyage_api_key_val(self) -> str:
		return self.VOYAGE_API_KEY.get_secret_value()

	@property
	def openai_api_key_val(self) -> str:
		return self.OPENAI_API_KEY.get_secret_value()

	@property
	def log_level_value(self) -> str:
		return self.LOG_LEVEL


# Singleton Accessor
settings = Settings()

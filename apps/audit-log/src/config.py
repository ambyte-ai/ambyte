from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	"""
	Configuration for the Audit Worker Service.
	Loads from environment variables (AMBYTE_AUDIT_*) or .env file.
	"""

	model_config = SettingsConfigDict(
		env_prefix='AMBYTE_AUDIT_',
		env_file='.env',
		env_ignore_empty=True,
		extra='ignore',
	)

	# Service Metadata
	SERVICE_NAME: str = 'audit-worker'
	ENVIRONMENT: str = 'local'
	LOG_LEVEL: str = 'INFO'
	HOST: str = '127.0.0.1'
	PORT: int = 8002

	# Database (Postgres)
	# We use the async psycopg driver for high-performance async I/O
	DATABASE_URL: str = 'postgresql+psycopg://postgres:postgres@db:5432/ambyte'

	# Redis (Stream Source)
	REDIS_URL: str = 'redis://redis:6379/0'

	# Worker Tuning
	# How many log entries to pull from Redis in a single XREADGROUP call
	BATCH_SIZE: int = 1000

	# Max time (seconds) to wait before flushing a partial batch to DB
	BATCH_FLUSH_INTERVAL: float = 1.0

	# How often to scan for new project streams (seconds)
	STREAM_DISCOVERY_INTERVAL: int = 10

	# Consumer Group Config
	CONSUMER_GROUP_NAME: str = 'audit_worker_group'
	CONSUMER_NAME: str = 'audit_worker_1'  # In K8s, use POD_NAME env var


settings = Settings()

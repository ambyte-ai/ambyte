import secrets
from typing import Annotated, Any, Literal

from pydantic import (
	AnyHttpUrl,
	BeforeValidator,
	PostgresDsn,
	computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
	"""
	Parses a comma-separated string of origins into a list.
	"""
	if isinstance(v, str) and not v.startswith('['):
		return [i.strip() for i in v.split(',')]
	elif isinstance(v, list | str):
		return v
	raise ValueError(v)


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		env_file='.env',
		env_ignore_empty=True,
		extra='ignore',
		case_sensitive=True,
	)

	# ==========================================================================
	# Core App Settings
	# ==========================================================================
	PROJECT_NAME: str = 'Ambyte Control Plane'
	VERSION: str = '0.1.0'
	API_V1_STR: str = '/v1'

	# ENVIRONMENT: local, staging, production
	ENVIRONMENT: Literal['local', 'staging', 'production'] = 'local'

	# ==========================================================================
	# Security
	# ==========================================================================
	# Used for cryptographic signing or internal hashing.
	# IN PROD: Change this via env var!
	SECRET_KEY: str = secrets.token_urlsafe(32)

	# Access token lifetime (for generated JWTs, if we roll our own)
	ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

	# CORS (Cross-Origin Resource Sharing)
	# Define who can talk to the API (e.g., your React dashboard).
	# Default allows localhost.
	BACKEND_CORS_ORIGINS: Annotated[list[AnyHttpUrl] | str, BeforeValidator(parse_cors)] = []

	# ==========================================================================
	# Database (PostgreSQL)
	# ==========================================================================
	POSTGRES_SERVER: str
	POSTGRES_PORT: int = 5432
	POSTGRES_USER: str
	POSTGRES_PASSWORD: str
	POSTGRES_DB: str = 'ambyte'

	@computed_field  # type: ignore[misc]
	@property
	def SQLALCHEMY_DATABASE_URI(self) -> str:
		"""
		Constructs the SQLAlchemy Async URI.
		We force the usage of the 'psycopg' driver here.
		"""
		return str(
			PostgresDsn.build(
				scheme='postgresql+psycopg',
				username=self.POSTGRES_USER,
				password=self.POSTGRES_PASSWORD,
				host=self.POSTGRES_SERVER,
				port=self.POSTGRES_PORT,
				path=self.POSTGRES_DB,
			)
		)

	# ==========================================================================
	# First User (Bootstrapping)
	# ==========================================================================
	# Optional: Used to create the first admin user in dev environments
	FIRST_SUPERUSER: str = 'admin@ambyte.ai'
	FIRST_SUPERUSER_PASSWORD: str = 'changethis'


# Singleton instance
settings = Settings()

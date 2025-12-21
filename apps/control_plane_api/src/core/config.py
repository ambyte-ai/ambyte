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
	# Used for internal hashing (API Keys), NOT for JWT signing anymore.
	# IN PROD: Change this via env var! # TODO
	SECRET_KEY: str = secrets.token_urlsafe(32)

	# CORS (Cross-Origin Resource Sharing)
	# Define who can talk to the API (e.g., your React dashboard).
	# Default allows localhost.
	BACKEND_CORS_ORIGINS: Annotated[list[AnyHttpUrl] | str, BeforeValidator(parse_cors)] = []

	# CLERK CONFIGURATION
	# Found in Clerk Dashboard -> API Keys -> Issuer
	# e.g., "https://clerk.ambyte.ai" or "https://humble-foal-12.clerk.accounts.dev"
	CLERK_ISSUER: str = 'https://quiet-slug-97.clerk.accounts.dev'

	# Expected Audience (usually empty for standard Clerk setups, but good practice to check)
	CLERK_AUDIENCE: str | None = None

	@computed_field
	@property
	def CLERK_JWKS_URL(self) -> str:
		"""Constructs the JWKS URL from the Issuer."""
		return f'{self.CLERK_ISSUER.rstrip("/")}/.well-known/jwks.json'

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
	# Caching (Redis)
	# ==========================================================================
	REDIS_HOST: str = 'localhost'
	REDIS_PORT: int = 6379
	REDIS_DB: int = 0
	REDIS_PASSWORD: str | None = None

	@computed_field
	@property
	def REDIS_URL(self) -> str:
		if self.REDIS_PASSWORD:
			return f'redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'
		return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'

	# ==========================================================================
	# First User (Bootstrapping)
	# ==========================================================================
	# Optional: Used to create the first admin user in dev environments
	FIRST_SUPERUSER: str = 'admin@ambyte.ai'
	FIRST_SUPERUSER_PASSWORD: str = 'changethis'


# Singleton instance
settings = Settings()

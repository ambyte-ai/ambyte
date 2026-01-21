import logging
from typing import Annotated, Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config as DatabricksSdkConfig
from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger('ambyte.connector.databricks')


def parse_csv(v: Any) -> list[str]:
	"""
	Parses a comma-separated string into a list of strings.
	Useful for env vars like INCLUDE_CATALOGS="sales,marketing"
	"""
	if isinstance(v, str):
		if not v.strip():
			return []
		return [i.strip() for i in v.split(',') if i.strip()]
	if isinstance(v, list):
		return v
	return []


class Settings(BaseSettings):
	"""
	Configuration for the Databricks Unity Catalog Connector.
	Loads from .env file or environment variables.
	"""

	model_config = SettingsConfigDict(
		env_prefix='AMBYTE_DATABRICKS_',
		env_file='.env',
		env_ignore_empty=True,
		extra='ignore',
	)

	LOCAL_MODE: bool = Field(
		default=False, description='If True, writes inventory to a local file instead of the Control Plane.'
	)

	# ==========================================================================
	# 1. Ambyte Control Plane Configuration
	# ==========================================================================
	CONTROL_PLANE_URL: Annotated[str, BeforeValidator(lambda v: str(v))] = Field(
		default='http://localhost:8000',  # TODO: change to api.ambyte.ai in prod
		description='Base URL of the Ambyte Control Plane API.',
	)

	CONNECTOR_API_KEY: SecretStr | None = Field(
		default=None,
		description='Machine API Key. Required if LOCAL_MODE is False.',
	)

	# ==========================================================================
	# 2. Databricks Authentication
	# ==========================================================================
	# Note: We rely on the Databricks SDK's unified auth, but explicit fields
	# allow for validation and overrides via AMBYTE_DATABRICKS_* prefixes.

	HOST: str = Field(
		...,
		description='Databricks Workspace URL (e.g., https://adb-1234.5.azuredatabricks.net)',
	)

	# Option A: Personal Access Token (PAT)
	TOKEN: SecretStr | None = Field(
		default=None,
		description='Personal Access Token for Databricks.',
	)

	# Option B: OAuth M2M (Service Principal)
	CLIENT_ID: str | None = Field(
		default=None,
		description='Service Principal Application ID.',
	)
	CLIENT_SECRET: SecretStr | None = Field(
		default=None,
		description='Service Principal Secret.',
	)

	# ==========================================================================
	# 3. Scoping & Filtering
	# ==========================================================================
	INCLUDE_CATALOGS: Annotated[list[str], BeforeValidator(parse_csv)] = Field(
		default=['*'],
		description="List of Catalogs to scan. Defaults to all ('*').",
	)

	EXCLUDE_CATALOGS: Annotated[list[str], BeforeValidator(parse_csv)] = Field(
		default=['system', 'hive_metastore', 'samples'],
		description='List of Catalogs to ignore.',
	)

	INCLUDE_SCHEMAS: Annotated[list[str], BeforeValidator(parse_csv)] = Field(
		default=['*'],
		description='List of Schemas to scan. Defaults to all.',
	)

	# ==========================================================================
	# 4. Helpers
	# ==========================================================================

	@model_validator(mode='after')
	def validate_auth_mode(self) -> 'Settings':
		# If we are NOT local, we MUST have an API Key to talk to the cloud
		if not self.LOCAL_MODE and not self.CONNECTOR_API_KEY:
			raise ValueError(
				'Missing AMBYTE_DATABRICKS_CONNECTOR_API_KEY. '
				'Set this to sync with the Cloud, or use --local to run offline.'
			)
		return self

	def get_databricks_client(self) -> WorkspaceClient:
		"""
		Returns an authenticated Databricks WorkspaceClient.
		"""
		# Construct SDK Config object
		db_config = DatabricksSdkConfig(
			host=self.HOST,
			token=self.TOKEN.get_secret_value() if self.TOKEN else None,
			client_id=self.CLIENT_ID,
			client_secret=self.CLIENT_SECRET.get_secret_value() if self.CLIENT_SECRET else None,
			# User agent helps Ambyte identify traffic source in Databricks audit logs
			product='ambyte-connector',
			product_version='0.1.0',
		)

		logger.info(f'Initializing Databricks Client for host: {self.HOST}')
		return WorkspaceClient(config=db_config)

	@property
	def control_plane_api_key_val(self) -> str:
		return self.CONNECTOR_API_KEY.get_secret_value() if self.CONNECTOR_API_KEY else ''


# Singleton instance
settings = Settings()

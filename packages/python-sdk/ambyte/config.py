from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AmbyteMode(StrEnum):
	"""
	Determines how the SDK resolves policy decisions.
	"""

	REMOTE = 'REMOTE'  # Connects to the centralized Control Plane API via HTTP.
	LOCAL = 'LOCAL'  # Loads a compiled policy artifact from disk (offline/testing).
	OFF = 'OFF'  # Disables all checks; always returns allowed (passthrough).


class AmbyteSettings(BaseSettings):
	"""
	Global configuration for the Ambyte SDK.
	Values are loaded from environment variables (e.g., AMBYTE_API_KEY).
	"""

	model_config = SettingsConfigDict(
		env_prefix='AMBYTE_',
		case_sensitive=False,
		env_file='.env',
		env_file_encoding='utf-8',
		extra='ignore',  # Ignore extra env vars not defined here
	)

	# ==========================================================================
	# Connectivity
	# ==========================================================================
	api_key: Annotated[
		SecretStr | None,
		Field(
			default=None,
			description='Authentication token for the Ambyte Control Plane.',
		),
	] = None
	control_plane_url: Annotated[
		HttpUrl,
		Field(
			description='The base URL of the Ambyte API.',
		),
	] = HttpUrl('http://localhost:8000')

	# ==========================================================================
	# Operational Behavior
	# ==========================================================================
	mode: AmbyteMode = Field(
		default=AmbyteMode.REMOTE,
		description='Operation mode: REMOTE, LOCAL, or OFF.',
	)
	fail_open: bool = Field(
		default=True,
		description=(
			'Safety mechanism. If True, network errors during permission checks '
			'will log a warning but Allow execution. If False, they raise an exception.'
		),
	)
	service_name: str = Field(
		default='unknown-service',
		description='Identifier for the application using this SDK (for lineage/audit).',
	)
	debug: bool = Field(
		default=False,
		description='If True, enables verbose logging of SDK internals.',
	)

	# ==========================================================================
	# Performance & Caching
	# ==========================================================================
	decision_cache_ttl_seconds: int = Field(
		default=60,
		ge=0,
		description='Time-to-live for policy decision results in local RAM.',
	)
	enable_background_sync: bool = Field(
		default=True,
		description='If True, audit logs and lineage events are sent asynchronously.',
	)
	batch_upload_interval_seconds: float = Field(
		default=5.0,
		description='How often (in seconds) the background worker flushes logs.',
	)

	# ==========================================================================
	# Local Mode Specifics
	# ==========================================================================
	local_policy_path: str | None = Field(
		default=None,
		description='Path to a JSON policy bundle when running in LOCAL mode.',
	)

	@field_validator('mode', mode='before')
	@classmethod
	def _case_insensitive_mode(cls, v: Any) -> Any:
		"""Ensure mode is upper-cased for enum validation."""
		if isinstance(v, str):
			return v.upper()
		return v

	@property
	def is_remote(self) -> bool:
		return self.mode == AmbyteMode.REMOTE

	@property
	def is_enabled(self) -> bool:
		return self.mode != AmbyteMode.OFF

	@property
	def api_key_value(self) -> str | None:
		"""Helper to expose SecretStr as string safely."""
		return self.api_key.get_secret_value() if self.api_key else None


# Singleton instance placeholder
# _settings_instance: Optional[AmbyteSettings] = None


@lru_cache
def get_config() -> AmbyteSettings:
	"""
	Returns the singleton configuration instance.
	The @lru_cache decorator handles caching, ensuring AmbyteSettings()
	is only instantiated once.
	"""
	return AmbyteSettings()


def reset_config():
	"""
	Resets the configuration. Useful for unit tests.
	"""
	# Simply clear the cache on the function to force a reload next time
	get_config.cache_clear()

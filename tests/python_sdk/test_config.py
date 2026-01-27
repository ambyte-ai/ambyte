import os
from unittest import mock

import pytest
from ambyte.config import AmbyteMode, get_config, reset_config
from pydantic import SecretStr, ValidationError


@pytest.fixture(autouse=True)
def clean_config_state():
	"""
	Fixture to ensure every test starts with a fresh configuration state.
	Runs before and after every test function.
	"""
	reset_config()
	yield
	reset_config()


def test_config_defaults(tmp_path):
	"""
	Verify that the SDK defaults to a safe REMOTE mode configuration
	if no environment variables are present.
	"""
	# Ensure no AMBYTE vars exist
	with mock.patch.dict(os.environ, {}, clear=True):
		# Switch to a temp directory to avoid picking up a local .env file
		old_cwd = os.getcwd()
		os.chdir(tmp_path)
		try:
			# Reset config to ensure AmbyteSettings re-instantiates in the new CWD
			reset_config()
			config = get_config()

			assert config.mode == AmbyteMode.REMOTE
			assert str(config.control_plane_url) == 'http://localhost:8000/'
			assert config.fail_open is True
			assert config.api_key is None
			assert config.service_name == 'unknown-service'

			# Check derived properties
			assert config.is_remote is True
			assert config.is_enabled is True
		finally:
			os.chdir(old_cwd)


def test_load_from_env_vars():
	"""
	Verify that environment variables (AMBYTE_*) correctly override defaults.
	"""
	env_vars = {
		'AMBYTE_API_KEY': 'sk_test_12345',
		'AMBYTE_CONTROL_PLANE_URL': 'https://api.ambyte.ai',
		'AMBYTE_MODE': 'LOCAL',
		'AMBYTE_FAIL_OPEN': 'false',
		'AMBYTE_SERVICE_NAME': 'payment-service',
		'AMBYTE_DECISION_CACHE_TTL_SECONDS': '300',
	}

	with mock.patch.dict(os.environ, env_vars):
		config = get_config()

		assert config.api_key == SecretStr('sk_test_12345')
		assert str(config.control_plane_url) == 'https://api.ambyte.ai/'
		assert config.mode == AmbyteMode.LOCAL
		assert config.fail_open is False
		assert config.service_name == 'payment-service'
		assert config.decision_cache_ttl_seconds == 300

		# Derived properties
		assert config.is_remote is False  # Because mode is LOCAL
		assert config.api_key_value == 'sk_test_12345'


def test_singleton_behavior():
	"""
	Verify that repeated calls to get_config() return the exact same object instance.
	"""
	cfg1 = get_config()
	cfg2 = get_config()

	assert cfg1 is cfg2
	assert id(cfg1) == id(cfg2)


def test_reset_behavior():
	"""
	Verify that reset_config() clears the cache and forces a reload.
	"""
	# 1. Load initial config
	cfg1 = get_config()

	# 2. Change env var (would usually be ignored by singleton)
	with mock.patch.dict(os.environ, {'AMBYTE_SERVICE_NAME': 'new-service'}):
		# 3. Reset
		reset_config()

		# 4. Load new config
		cfg2 = get_config()

	assert cfg1 is not cfg2
	assert cfg1.service_name == 'unknown-service'  # Old instance remains unchanged
	assert cfg2.service_name == 'new-service'  # New instance picked up the change


def test_mode_parsing():
	"""
	Test that AmbyteMode enum handles string inputs case-insensitively via Pydantic.
	"""
	with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'off'}):
		config = get_config()
		assert config.mode == AmbyteMode.OFF
		assert config.is_enabled is False

	reset_config()

	with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'remote'}):
		config = get_config()
		assert config.mode == AmbyteMode.REMOTE


def test_invalid_url_validation():
	"""
	Ensure invalid URLs raise a validation error.
	"""
	with mock.patch.dict(os.environ, {'AMBYTE_CONTROL_PLANE_URL': 'not-a-url'}):
		with pytest.raises(ValidationError):
			get_config()

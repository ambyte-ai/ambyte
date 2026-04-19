import os
from unittest.mock import patch

import pytest
from ambyte_databricks.config import Settings, parse_csv
from pydantic import ValidationError

# ==============================================================================
# 1. HELPER FUNCTION TESTS
# ==============================================================================


@pytest.mark.parametrize(
	'input_val, expected',
	[
		(None, []),
		('', []),
		('   ', []),
		('cat1', ['cat1']),
		('cat1,cat2', ['cat1', 'cat2']),
		('  cat1 ,  cat2  ', ['cat1', 'cat2']),  # Whitespace stripping
		(['cat1', 'cat2'], ['cat1', 'cat2']),  # Passthrough
	],
)
def test_parse_csv(input_val, expected):
	"""Verify comma-separated string parsing logic."""
	assert parse_csv(input_val) == expected


# ==============================================================================
# 2. SETTINGS LOAD & VALIDATION TESTS
# ==============================================================================


def test_settings_load_happy_path(mock_env_vars, monkeypatch):
	"""
	Verify Settings load correctly from the environment variables
	defined in conftest.py.
	"""
	# Override/Ensure the specific alias Pydantic looks for is set
	overrides = {'AMBYTE_API_KEY': 'sk_test_mock_key'}

	# We layer this on top of the conftest mock
	with patch.dict(os.environ, overrides):
		settings = Settings()

		assert settings.HOST == 'https://test.databricks.com'
		assert settings.TOKEN.get_secret_value() == 'dapi_test_token'
		assert settings.control_plane_api_key_val == 'sk_test_mock_key'
		assert settings.WAREHOUSE_ID == 'wh_123456789'
		assert settings.LOCAL_MODE is False

		# Check default list parsing
		assert settings.INCLUDE_CATALOGS == ['*']
		assert settings.EXCLUDE_CATALOGS == ['system', 'hive_metastore', 'samples']


def test_settings_list_parsing_overrides():
	"""Verify env vars override defaults for list fields."""
	# Note: pydantic-settings parses list fields as JSON by default.
	# We provide JSON arrays here to pass the EnvSettingsSource parsing.
	env_overrides = {
		'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
		'AMBYTE_API_KEY': 'sk_key',
		'AMBYTE_DATABRICKS_INCLUDE_CATALOGS': '["sales", "marketing"]',
		'AMBYTE_DATABRICKS_EXCLUDE_SCHEMAS': '["temp_*", "garbage"]',
	}

	with patch.dict(os.environ, env_overrides, clear=True):
		settings = Settings()
		assert settings.INCLUDE_CATALOGS == ['sales', 'marketing']
		assert settings.EXCLUDE_SCHEMAS == ['temp_*', 'garbage']


def test_validation_error_missing_api_key_in_remote_mode():
	"""
	Should raise ValueError if LOCAL_MODE is False (default)
	and no API Key is provided.
	"""
	# Override the fixture's env vars to remove the key
	env_vars = {
		'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
		'AMBYTE_DATABRICKS_LOCAL_MODE': 'false',
		# Missing AMBYTE_DATABRICKS_API_KEY
	}

	with patch.dict(os.environ, env_vars, clear=True):
		with pytest.raises(ValidationError) as exc:
			Settings(_env_file=None)
		assert 'Missing AMBYTE_DATABRICKS_API_KEY' in str(exc.value)


def test_validation_success_local_mode_no_key():
	"""
	Should PASS if LOCAL_MODE is True, even without an API Key.
	"""
	env_vars = {
		'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
		'AMBYTE_DATABRICKS_LOCAL_MODE': 'true',
		# No API Key
	}

	with patch.dict(os.environ, env_vars, clear=True):
		settings = Settings(_env_file=None)
		assert settings.LOCAL_MODE is True
		assert settings.API_KEY is None
		assert settings.control_plane_api_key_val == ''


def test_api_key_alias_support():
	"""Verify AMBYTE_API_KEY works as an alias for CONNECTOR_API_KEY."""
	env_vars = {'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com', 'AMBYTE_API_KEY': 'sk_aliased_key'}

	with patch.dict(os.environ, env_vars, clear=True):
		settings = Settings()
		assert settings.API_KEY.get_secret_value() == 'sk_aliased_key'


# ==============================================================================
# 3. CLIENT FACTORY TESTS
# ==============================================================================


@patch('ambyte_databricks.config.DatabricksSdkConfig')
@patch('ambyte_databricks.config.WorkspaceClient')
def test_get_databricks_client_pat(mock_ws_client_cls, mock_config_cls, mock_env_vars):
	"""Verify PAT authentication config."""
	settings = Settings(_env_file=None)

	_ = settings.get_databricks_client()

	# 1. Verify DatabricksSdkConfig was initialized with correct arguments
	mock_config_cls.assert_called_once()
	_, kwargs = mock_config_cls.call_args

	assert kwargs['host'] == 'https://test.databricks.com'
	assert kwargs['token'] == 'dapi_test_token'
	assert kwargs['product'] == 'ambyte-connector'

	# 2. Verify WorkspaceClient was initialized with the config instance
	mock_ws_client_cls.assert_called_once_with(config=mock_config_cls.return_value)


@patch('ambyte_databricks.config.DatabricksSdkConfig')
@patch('ambyte_databricks.config.WorkspaceClient')
def test_get_databricks_client_oauth(mock_ws_client_cls, mock_config_cls):
	"""Verify Service Principal authentication config."""
	env_vars = {
		'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
		'AMBYTE_DATABRICKS_CLIENT_ID': 'client-id-123',
		'AMBYTE_DATABRICKS_CLIENT_SECRET': 'secret-456',
		'AMBYTE_API_KEY': 'sk_key',
	}

	with patch.dict(os.environ, env_vars, clear=True):
		settings = Settings(_env_file=None)
		_ = settings.get_databricks_client()

		mock_config_cls.assert_called_once()
		_, kwargs = mock_config_cls.call_args

		assert kwargs['client_id'] == 'client-id-123'
		assert kwargs['client_secret'] == 'secret-456'

		mock_ws_client_cls.assert_called_once_with(config=mock_config_cls.return_value)

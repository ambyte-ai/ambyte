import os
from pathlib import Path
from unittest import mock

import pytest
from ambyte_cli.config import (
	AmbyteConfig,
	CloudConfig,
	TargetPlatform,
	get_workspace_root,
	load_config,
	save_config,
)

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def temp_workspace(tmp_path):
	"""
	Sets up a temporary directory and changes the CWD to it.
	Restores original CWD after test.
	"""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)
	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


@pytest.fixture
def setup_valid_workspace(temp_workspace):
	"""
	Creates the .ambyte folder in the temp workspace so get_workspace_root works.
	"""
	config_dir = temp_workspace / '.ambyte'
	config_dir.mkdir()
	return temp_workspace


# ==============================================================================
# TESTS: Model Defaults
# ==============================================================================


def test_ambyte_config_defaults():
	"""Verify default values for a new configuration."""
	conf = AmbyteConfig(project_name='test-project')

	assert conf.project_name == 'test-project'
	assert conf.version == '1.0'
	assert conf.targets == [TargetPlatform.LOCAL]
	assert conf.policies_dir == Path('policies')
	assert conf.artifacts_dir == Path('.ambyte/dist')

	# Cloud defaults
	assert str(conf.cloud.url) == 'https://api.ambyte.ai/'
	assert conf.cloud.organization_id is None


def test_ambyte_config_custom_paths():
	"""Verify path overrides work."""
	conf = AmbyteConfig(project_name='custom', policies_dir='src/policies', resources_dir='inventory')
	assert conf.policies_dir == Path('src/policies')
	assert conf.resources_dir == Path('inventory')


# ==============================================================================
# TESTS: Workspace Resolution (get_workspace_root)
# ==============================================================================


def test_get_workspace_root_current_dir(setup_valid_workspace):
	"""Should find root when .ambyte is in the current directory."""
	found = get_workspace_root()
	assert found == setup_valid_workspace


def test_get_workspace_root_from_subdir(setup_valid_workspace):
	"""Should find root when traversing up from a deep subdirectory."""
	# Create deep structure
	deep_dir = setup_valid_workspace / 'apps' / 'backend' / 'src'
	deep_dir.mkdir(parents=True)

	os.chdir(deep_dir)

	found = get_workspace_root()
	assert found == setup_valid_workspace


def test_get_workspace_root_missing():
	"""
	Should raise FileNotFoundError if no .ambyte directory exists in hierarchy.
	We mock the filesystem traversal to ensure no parent directories (like ~/.ambyte)
	trigger a false positive.
	"""
	with mock.patch('ambyte_cli.config.Path.cwd') as mock_cwd:
		# Create a mock path object that simulates being at the root (no parents)
		mock_path = mock.MagicMock()
		mock_cwd.return_value = mock_path
		mock_path.parents = []

		# Ensure the check (path / CONFIG_DIR_NAME).exists() returns False
		# __truediv__ handles the / operator
		mock_path.__truediv__.return_value.exists.return_value = False
		mock_path.__truediv__.return_value.is_dir.return_value = False

		with pytest.raises(FileNotFoundError) as exc:
			get_workspace_root()

	assert "Run 'ambyte init' first" in str(exc.value)


# ==============================================================================
# TESTS: Load / Save Logic
# ==============================================================================


def test_save_and_load_roundtrip(temp_workspace):
	"""
	Verify we can save an AmbyteConfig object to disk and load it back identically.
	"""
	# Create original config
	original = AmbyteConfig(
		project_name='roundtrip',
		targets=[TargetPlatform.SNOWFLAKE, TargetPlatform.OPA],
		cloud=CloudConfig(organization_id='org_123'),
	)

	# Save
	save_config(original, temp_workspace)

	# Verify file exists
	config_file = temp_workspace / '.ambyte' / 'config.yaml'
	assert config_file.exists()

	# Load (load_config uses get_workspace_root, so we must be in valid workspace)
	# verify logic works implicitly via CWD
	loaded = load_config()

	assert loaded.project_name == original.project_name
	assert len(loaded.targets) == 2
	assert TargetPlatform.SNOWFLAKE in loaded.targets
	assert loaded.cloud.organization_id == 'org_123'


def test_absolute_property_paths(setup_valid_workspace):
	"""
	Verify the .abs_* properties correctly resolve relative to the workspace root.
	"""
	conf = AmbyteConfig(project_name='abs_test', policies_dir='custom_pols')
	# We cheat and mock the save to disk so get_workspace_root is happy
	save_config(conf, setup_valid_workspace)

	loaded = load_config()

	expected_policies = setup_valid_workspace / 'custom_pols'
	assert loaded.abs_policies_dir == expected_policies
	assert loaded.abs_policies_dir.is_absolute()


# ==============================================================================
# TESTS: Error Handling
# ==============================================================================


def test_load_config_invalid_yaml(setup_valid_workspace, capsys):
	"""
	Should exit gracefully (sys.exit) if YAML is malformed.
	"""
	config_file = setup_valid_workspace / '.ambyte' / 'config.yaml'
	config_file.write_text("project_name: 'broken\n  indentation: error", encoding='utf-8')

	with pytest.raises(SystemExit) as exc:
		load_config()

	assert exc.value.code == 1
	captured = capsys.readouterr()
	assert '[ERROR] Failed to parse YAML' in captured.out


def test_load_config_invalid_schema(setup_valid_workspace, capsys):
	"""
	Should exit gracefully if YAML is valid but violates Pydantic schema
	(e.g., missing required field 'project_name').
	"""
	config_file = setup_valid_workspace / '.ambyte' / 'config.yaml'
	# Missing project_name
	config_file.write_text("version: '1.0'", encoding='utf-8')

	with pytest.raises(SystemExit) as exc:
		load_config()

	assert exc.value.code == 1
	captured = capsys.readouterr()
	assert '[ERROR] Invalid configuration' in captured.out
	assert 'project_name' in captured.out

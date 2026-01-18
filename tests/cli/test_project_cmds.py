import os

import pytest
from ambyte_cli.config import CONFIG_DIR_NAME
from ambyte_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def temp_cwd(tmp_path):
	"""
	Sets the Current Working Directory to a temp folder for the duration of the test.
	This ensures `ambyte init` creates files in isolation.
	"""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)
	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


# ==============================================================================
# TEST: ambyte init
# ==============================================================================


def test_init_scaffolding_defaults(temp_cwd):
	"""
	Test 'ambyte init' with prompts (simulated via input).
	"""
	# Inputs: Project Name, Use Snowflake?
	result = runner.invoke(app, ['init'], input='MyProject\ny\n')

	assert result.exit_code == 0
	assert 'Workspace initialized successfully' in result.stdout

	# 1. Check Config
	config_path = temp_cwd / CONFIG_DIR_NAME / 'config.yaml'
	assert config_path.exists()
	content = config_path.read_text()
	assert 'project_name: MyProject' in content
	assert 'snowflake' in content  # From the 'y' prompt

	# 2. Check Directories
	assert (temp_cwd / 'policies').exists()
	assert (temp_cwd / 'resources').exists()

	# 3. Check Sample Files
	assert (temp_cwd / 'policies' / 'gdpr_sample.yaml').exists()
	assert (temp_cwd / 'resources' / 'resources.yaml').exists()


def test_init_non_interactive(temp_cwd):
	"""
	Test 'ambyte init --yes' (defaults).
	"""
	# Default name is directory name (tmp path name)
	dirname = temp_cwd.name

	result = runner.invoke(app, ['init', '--yes'])

	assert result.exit_code == 0

	config_path = temp_cwd / CONFIG_DIR_NAME / 'config.yaml'
	content = config_path.read_text()

	# Check default name usage
	assert f'project_name: {dirname}' in content
	# Non-interactive defaults to just LOCAL target usually
	assert 'snowflake' not in content


def test_init_overwrite_prompt(temp_cwd):
	"""
	Test handling when .ambyte already exists.
	"""
	# 1. Create existing
	(temp_cwd / CONFIG_DIR_NAME).mkdir()

	# 2. Run init -> Prompt -> Say 'n' (No)
	result = runner.invoke(app, ['init'], input='n\n')

	assert result.exit_code == 1
	assert 'Aborted' in result.stdout


def test_init_overwrite_force(temp_cwd):
	"""
	Test overwriting with --yes flag or explicit confirmation.
	"""
	(temp_cwd / CONFIG_DIR_NAME).mkdir()

	# Prompt -> Say 'y'
	result = runner.invoke(app, ['init'], input='y\nMyProject\nn\n')

	assert result.exit_code == 0
	assert 'Workspace initialized successfully' in result.stdout


# ==============================================================================
# TEST: ambyte validate
# ==============================================================================


def test_validate_no_workspace(temp_cwd):
	"""
	Running validate outside a workspace should fail.
	"""
	result = runner.invoke(app, ['validate'])

	assert result.exit_code == 1
	assert 'Not an Ambyte workspace' in result.stdout


def test_validate_success(temp_cwd):
	"""
	Validate a workspace with the sample policy.
	"""
	# Setup workspace
	runner.invoke(app, ['init', '--yes'])

	# Run validate
	result = runner.invoke(app, ['validate'])

	assert result.exit_code == 0
	assert 'Success!' in result.stdout
	assert 'Validated 1 obligation' in result.stdout


def test_validate_failure_bad_yaml(temp_cwd):
	"""
	Validate should report errors if a policy file is broken.
	"""
	runner.invoke(app, ['init', '--yes'])

	# Corrupt the sample file
	sample = temp_cwd / 'policies' / 'gdpr_sample.yaml'
	sample.write_text('id: [unclosed list')

	result = runner.invoke(app, ['validate'])

	# Since we corrupted the only file, it should exit 1.
	assert result.exit_code == 1
	assert 'Error loading' in result.stdout
	assert 'Invalid YAML' in result.stdout


def test_validate_failure_schema_error(temp_cwd):
	"""
	Validate should catch Pydantic schema errors (e.g. missing fields).
	"""
	runner.invoke(app, ['init', '--yes'])

	# Write invalid schema file
	bad_file = temp_cwd / 'policies' / 'bad.yaml'
	bad_file.write_text("""
    # Missing ID and Title
    description: "Invalid"
    provenance: {source_id: "X", document_type: "Y"}
    constraint: {type: "RETENTION"}
    """)

	result = runner.invoke(app, ['validate'])

	# if at least one is good, it exits 0.
	assert result.exit_code == 0

	# Verify that errors are reported.
	# The output format is: "Error loading policy: File bad.yaml: ..."
	assert 'Error loading policy' in result.stdout
	assert 'bad.yaml' in result.stdout
	assert 'Validation Failed' in result.stdout

	# Ensure the valid one still passed
	assert 'Validated 1 obligation' in result.stdout

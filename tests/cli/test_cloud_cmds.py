import os
import textwrap
from pathlib import Path
from unittest import mock

import httpx
import pytest
from ambyte_cli.config import load_config, save_config
from ambyte_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def initialized_workspace(tmp_path):
	"""Sets up an initialized .ambyte workspace."""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)
	runner.invoke(app, ['init', '--yes', '--name', 'test-cloud-project'])
	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


def link_project(workspace_path: Path, project_id: str = '00000000-0000-0000-0000-000000000001'):
	"""Helper to simulate 'ambyte login' having linked a project to the local config."""
	cfg = load_config()
	cfg.cloud.project_id = project_id
	save_config(cfg, workspace_path)


# ==============================================================================
# LOGIN COMMAND TESTS
# ==============================================================================


def test_login_already_authenticated_env(monkeypatch, capsys):
	"""Should exit early if AMBYTE_API_KEY is in env."""
	monkeypatch.setenv('AMBYTE_API_KEY', 'sk_live_env_key')
	result = runner.invoke(app, ['login'])
	assert 'Authenticated via environment/credentials. Linking project...' in result.stdout


def test_login_manual_paste_success(no_credentials, initialized_workspace):
	"""Tests Option 3: Manual API Key paste."""

	mock_user_data = {
		'user': {'email': 'test@ambyte.ai'},
		'organization_id': 'org-123',
		'projects': [{'id': 'proj-abc', 'name': 'Cloud Project'}],
	}

	with mock.patch('httpx.Client.get') as mock_get:
		mock_get.return_value = mock.Mock(status_code=200, json=lambda: mock_user_data)

		# Choice 3 (Paste), Then the key, then Choice 1 (Project #1)
		result = runner.invoke(app, ['login'], input='3\nsk_live_pasted_key\n1\n')

		assert result.exit_code == 0
		assert 'Authenticated as test@ambyte.ai' in result.stdout
		assert 'Default project set to: Cloud Project' in result.stdout


def test_login_oidc_browser_flow(no_credentials, initialized_workspace):
	"""Tests Option 1: Web Browser (OIDC) flow."""

	state_val = 'secure-state-123'
	mock_user_data = {
		'user': {'email': 'browser@ambyte.ai'},
		'organization_id': 'org-456',
		'projects': [{'id': 'proj-789', 'name': 'Web Project'}],
	}

	with (
		mock.patch('ambyte_cli.services.oidc.OidcService.get_auth_url', return_value=('http://login', state_val)),
		mock.patch('ambyte_cli.services.oidc.OidcService.open_browser') as mock_browser,
		mock.patch(
			'ambyte_cli.services.oidc.OidcService.wait_for_token',
			return_value={'token': 'jwt-token', 'state': state_val},
		),
		mock.patch('httpx.Client.get') as mock_get,
		mock.patch('httpx.Client.post') as mock_post,
	):
		# Mock identity fetch (WhoAmI)
		mock_get.return_value = mock.Mock(status_code=200, json=lambda: mock_user_data)
		# Mock machine key exchange
		mock_post.return_value = mock.Mock(status_code=200, json=lambda: {'key': 'sk_live_generated_key'})

		# Choice 1 (Browser), then Choice 1 (Project)
		result = runner.invoke(app, ['login'], input='1\n1\n')

		assert result.exit_code == 0
		mock_browser.assert_called_once()
		assert 'Success!' in result.stdout


# ==============================================================================
# PUSH COMMAND TESTS
# ==============================================================================


def test_push_validation_error(initialized_workspace, mock_credentials_file):
	"""Should abort push if local policies have syntax errors."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# Create a broken policy
	(initialized_workspace / 'policies' / 'broken.yaml').write_text('id: [unclosed list', encoding='utf-8')

	result = runner.invoke(app, ['push'])
	assert result.exit_code == 1
	assert 'Validation Failed' in result.stdout


def test_push_success_batch(initialized_workspace, mock_credentials_file):
	"""Happy path for batch push."""
	mock_credentials_file()
	link_project(initialized_workspace)

	mock_resp = [{'slug': 'p1', 'status': 'CREATED', 'version': 1, 'title': 'T'}]

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.push_obligations', return_value=mock_resp):
		result = runner.invoke(app, ['push'], input='y\n')
		assert result.exit_code == 0
		assert 'Sync Successful' in result.stdout


def test_push_dry_run(initialized_workspace, mock_credentials_file):
	"""Verify dry-run doesn't ask for confirmation and prints appropriate header."""
	link_project(initialized_workspace)
	mock_credentials_file()

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.push_obligations', return_value=[]):
		result = runner.invoke(app, ['push', '--dry-run'])
		assert 'DRY RUN MODE' in result.stdout


# ==============================================================================
# PULL COMMAND TESTS
# ==============================================================================


def test_pull_not_authenticated(no_credentials, initialized_workspace):
	"""Pull should fail if no API key is found."""
	result = runner.invoke(app, ['pull'])
	assert result.exit_code == 1
	assert 'Not authenticated' in result.stdout


def test_pull_success(initialized_workspace, mock_credentials_file):
	"""Happy path for pull."""
	mock_credentials_file()
	link_project(initialized_workspace)

	remote_obs = [
		{
			'id': 'remote-p1',
			'title': 'Cloud Policy',
			'description': '...',
			'provenance': {'source_id': 'R', 'document_type': 'REG'},
			'enforcement_level': '1',
			'retention': {'duration': 'PT100S', 'trigger': '1'},
		}
	]

	with mock.patch('ambyte.client.AmbyteClient.list_obligations', return_value=remote_obs):
		result = runner.invoke(app, ['pull'])
		assert result.exit_code == 0
		assert 'remote-p1' in result.stdout
		assert (initialized_workspace / 'policies' / 'remote-p1.yaml').exists()


def test_pull_prune_locally(initialized_workspace, mock_credentials_file):
	"""Pull with --prune should delete local files not in remote."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# 1. Create a VALID local file that "doesn't exist" in remote
	local_extra = initialized_workspace / 'policies' / 'orphan.yaml'
	local_extra.write_text(
		textwrap.dedent("""
        id: orphan
        title: Orphan Policy
        provenance:
            source_id: "TEST"
            document_type: "INTERNAL"
        retention:
            duration: "1d"
            trigger: "CREATION_DATE"
    """),
		encoding='utf-8',
	)

	# 2. Remote is empty
	with mock.patch('ambyte.client.AmbyteClient.list_obligations', return_value=[]):
		# Run pull with prune, confirm 'y'
		result = runner.invoke(app, ['pull', '--prune'], input='y\n')

		assert result.exit_code == 0
		assert 'DELETED' in result.stdout
		assert 'orphan' in result.stdout
		assert not local_extra.exists()


# ==============================================================================
# ERROR HANDLING TESTS
# ==============================================================================


def test_api_client_http_errors(initialized_workspace, mock_credentials_file):
	"""Directly test API client error formatting for coverage."""
	from ambyte_cli.config import load_config
	from ambyte_cli.services.api_client import CloudApiClient

	mock_credentials_file()
	link_project(initialized_workspace)
	client = CloudApiClient(load_config())

	# Create a mock HTTP response
	response = mock.Mock(spec=httpx.Response)
	response.json.return_value = {'detail': 'Specific Error'}
	response.text = 'Raw Error'

	# Test 401
	response.status_code = 401
	with mock.patch('ambyte_cli.ui.console.console.print') as mock_print:
		client._handle_http_error(httpx.HTTPStatusError('Err', request=mock.Mock(), response=response))
		assert 'Authentication Failed' in mock_print.call_args[0][0]

	# Test 404
	response.status_code = 404
	with mock.patch('ambyte_cli.ui.console.console.print') as mock_print:
		client._handle_http_error(httpx.HTTPStatusError('Err', request=mock.Mock(), response=response))
		assert 'Resource Not Found' in mock_print.call_args[0][0]

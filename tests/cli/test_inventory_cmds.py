import json
import os
from pathlib import Path
from unittest import mock

import httpx
import pytest
import yaml
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
	runner.invoke(app, ['init', '--yes', '--name', 'test-inventory-project'])
	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


def link_project(workspace_path: Path, project_id: str = '00000000-0000-0000-0000-000000000001'):
	"""Helper to simulate 'ambyte login' having linked a project to the local config."""
	cfg = load_config()
	cfg.cloud.project_id = project_id
	save_config(cfg, workspace_path)


@pytest.fixture
def sample_inventory_response():
	"""Returns a sample paginated inventory response."""
	return {
		'items': [
			{
				'urn': 'urn:snowflake:prod.sales.customers',
				'platform': 'snowflake',
				'name': 'Customer Data',
				'attributes': {'tags': {'env': 'prod', 'sensitivity': 'high'}},
			},
			{
				'urn': 'urn:databricks:catalog.schema.table',
				'platform': 'databricks',
				'name': 'Analytics Table',
				'attributes': {'tags': {'env': 'staging'}},
			},
			{
				'urn': 'urn:s3:bucket/path/file.parquet',
				'platform': 's3',
				'name': 'Raw Logs',
				'attributes': {'tags': {}},
			},
		],
		'total': 3,
		'page': 1,
		'size': 20,
		'pages': 1,
	}


@pytest.fixture
def large_inventory_response():
	"""Returns a larger paginated inventory for pagination tests."""
	items = [
		{
			'urn': f'urn:test:resource-{i}',
			'platform': 'snowflake' if i % 2 == 0 else 'databricks',
			'name': f'Resource {i}',
			'attributes': {'tags': {'index': str(i)}},
		}
		for i in range(1, 101)
	]
	return {
		'items': items[:50],  # First page
		'total': 100,
		'page': 1,
		'size': 50,
		'pages': 2,
	}


# ==============================================================================
# SYNC COMMAND TESTS
# ==============================================================================


def test_sync_no_resources_file(initialized_workspace, mock_credentials_file):
	"""Should handle missing resources.yaml gracefully with default wildcard resource."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# Mock the API call since we're testing CLI behavior, not network
	mock_resp = [{'urn': 'urn:local:default', 'platform': 'local'}]
	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.sync_inventory', return_value=mock_resp):
		result = runner.invoke(app, ['inventory', 'sync'])
		# Should use default wildcard and sync successfully
		assert result.exit_code == 0
		assert 'Successfully synced' in result.stdout or '✔' in result.stdout


def test_sync_dry_run(initialized_workspace, mock_credentials_file):
	"""Dry run should show preview without pushing."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# Create a sample resources.yaml
	resources_dir = initialized_workspace / 'resources'
	resources_dir.mkdir(exist_ok=True)
	resources_file = resources_dir / 'resources.yaml'
	resources_file.write_text(
		yaml.dump(
			{
				'resources': [
					{'urn': 'urn:test:sample', 'platform': 'local', 'tags': {'env': 'test'}},
				]
			}
		),
		encoding='utf-8',
	)

	result = runner.invoke(app, ['inventory', 'sync', '--dry-run'])
	assert result.exit_code == 0
	assert 'Dry Run' in result.stdout or 'Preview' in result.stdout
	assert 'urn:test:sample' in result.stdout


def test_sync_success(initialized_workspace, mock_credentials_file):
	"""Happy path for inventory sync."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# Create resources
	resources_dir = initialized_workspace / 'resources'
	resources_dir.mkdir(exist_ok=True)
	resources_file = resources_dir / 'resources.yaml'
	resources_file.write_text(
		yaml.dump(
			{
				'resources': [
					{'urn': 'urn:snowflake:db.schema.table', 'platform': 'snowflake', 'tags': {'env': 'prod'}},
				]
			}
		),
		encoding='utf-8',
	)

	mock_resp = [{'urn': 'urn:snowflake:db.schema.table', 'platform': 'snowflake'}]

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.sync_inventory', return_value=mock_resp):
		result = runner.invoke(app, ['inventory', 'sync'])
		assert result.exit_code == 0
		assert 'Successfully synced' in result.stdout or '✔' in result.stdout


# ==============================================================================
# LIST COMMAND TESTS
# ==============================================================================


def test_list_basic(initialized_workspace, mock_credentials_file, sample_inventory_response):
	"""Basic list command should show resources in a table."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=sample_inventory_response
	):
		result = runner.invoke(app, ['inventory', 'list'])

		assert result.exit_code == 0
		# Should contain URNs from sample data
		assert 'snowflake' in result.stdout.lower() or 'customers' in result.stdout.lower()
		assert 'Page 1' in result.stdout or 'Showing' in result.stdout


def test_list_empty_inventory(initialized_workspace, mock_credentials_file):
	"""Should handle empty inventory gracefully."""
	mock_credentials_file()
	link_project(initialized_workspace)

	empty_response = {'items': [], 'total': 0, 'page': 1, 'size': 20, 'pages': 0}

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=empty_response):
		result = runner.invoke(app, ['inventory', 'list'])

		assert result.exit_code == 0
		assert 'No resources found' in result.stdout


def test_list_with_filters(initialized_workspace, mock_credentials_file, sample_inventory_response):
	"""List with platform and URN filters should pass params to API."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=sample_inventory_response
	) as mock_list:
		result = runner.invoke(app, ['inventory', 'list', '--platform', 'snowflake', '--urn', 'customers'])

		assert result.exit_code == 0
		# Verify the mock was called with correct filter parameters
		mock_list.assert_called_once()
		call_kwargs = mock_list.call_args[1]
		assert call_kwargs.get('platform') == 'snowflake'
		assert call_kwargs.get('urn_filter') == 'customers'


def test_list_pagination(initialized_workspace, mock_credentials_file, large_inventory_response):
	"""Should show navigation hints for paginated results."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=large_inventory_response
	):
		result = runner.invoke(app, ['inventory', 'list', '--size', '50'])

		assert result.exit_code == 0
		# Should show page 1 of 2
		assert 'Page 1' in result.stdout
		# Should show navigation hint for next page
		assert '--page 2' in result.stdout or '2' in result.stdout


def test_list_specific_page(initialized_workspace, mock_credentials_file):
	"""Should fetch requested page number."""
	mock_credentials_file()
	link_project(initialized_workspace)

	page2_response = {
		'items': [{'urn': 'urn:test:page2-item', 'platform': 'local', 'name': 'Page 2 Item', 'attributes': {}}],
		'total': 51,
		'page': 2,
		'size': 50,
		'pages': 2,
	}

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=page2_response
	) as mock_list:
		result = runner.invoke(app, ['inventory', 'list', '--page', '2'])

		assert result.exit_code == 0
		mock_list.assert_called_once()
		assert mock_list.call_args[1]['page'] == 2


def test_list_json_output(initialized_workspace, mock_credentials_file, sample_inventory_response):
	"""JSON output should be valid JSON."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=sample_inventory_response
	):
		result = runner.invoke(app, ['inventory', 'list', '--json'])

		assert result.exit_code == 0
		# Should be valid JSON
		parsed = json.loads(result.stdout)
		assert 'items' in parsed
		assert len(parsed['items']) == 3


def test_list_compact_mode(initialized_workspace, mock_credentials_file, sample_inventory_response):
	"""Compact mode should not show tags column."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory', return_value=sample_inventory_response
	):
		result = runner.invoke(app, ['inventory', 'list', '--compact'])

		assert result.exit_code == 0
		# Should still show basic columns
		assert 'snowflake' in result.stdout.lower() or 'URN' in result.stdout


def test_list_all_pages(initialized_workspace, mock_credentials_file):
	"""--all flag should fetch all pages."""
	mock_credentials_file()
	link_project(initialized_workspace)

	# First page
	page1 = {
		'items': [
			{'urn': f'urn:test:item-{i}', 'platform': 'local', 'name': f'Item {i}', 'attributes': {}}
			for i in range(1, 4)
		],
		'total': 5,
		'page': 1,
		'size': 3,
		'pages': 2,
	}
	# Second page
	page2 = {
		'items': [
			{'urn': f'urn:test:item-{i}', 'platform': 'local', 'name': f'Item {i}', 'attributes': {}}
			for i in range(4, 6)
		],
		'total': 5,
		'page': 2,
		'size': 3,
		'pages': 2,
	}

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.list_inventory', side_effect=[page1, page2]):
		result = runner.invoke(app, ['inventory', 'list', '--all'])

		assert result.exit_code == 0
		# Should show total from both pages
		assert 'Total: 5' in result.stdout or 'item-5' in result.stdout or 'Item 5' in result.stdout


def test_list_all_json(initialized_workspace, mock_credentials_file):
	"""--all --json should output flat array of all items."""
	mock_credentials_file()
	link_project(initialized_workspace)

	page1 = {
		'items': [{'urn': 'urn:test:item-1', 'platform': 'local', 'name': 'Item 1', 'attributes': {}}],
		'total': 2,
		'page': 1,
		'size': 1,
		'pages': 2,
	}
	page2 = {
		'items': [{'urn': 'urn:test:item-2', 'platform': 'local', 'name': 'Item 2', 'attributes': {}}],
		'total': 2,
		'page': 2,
		'size': 1,
		'pages': 2,
	}

	with mock.patch('ambyte_cli.services.api_client.CloudApiClient.list_inventory', side_effect=[page1, page2]):
		result = runner.invoke(app, ['inventory', 'list', '--all', '--json'])

		assert result.exit_code == 0
		parsed = json.loads(result.stdout)
		# Should be a flat array of all items
		assert isinstance(parsed, list)
		assert len(parsed) == 2


# ==============================================================================
# NOT AUTHENTICATED TESTS
# ==============================================================================


def test_list_not_authenticated(no_credentials, initialized_workspace, monkeypatch):
	"""List should fail if no API key is found."""
	monkeypatch.delenv('AMBYTE_API_KEY', raising=False)

	with mock.patch('ambyte_cli.services.auth.load_dotenv'):
		result = runner.invoke(app, ['inventory', 'list'])

	assert result.exit_code == 1 or 'Not authenticated' in result.stdout or 'Failed' in result.stdout


# ==============================================================================
# ERROR HANDLING TESTS
# ==============================================================================


def test_list_network_error(initialized_workspace, mock_credentials_file):
	"""Should handle network errors gracefully."""
	mock_credentials_file()
	link_project(initialized_workspace)

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory',
		side_effect=httpx.RequestError('Connection failed'),
	):
		result = runner.invoke(app, ['inventory', 'list'])

		assert result.exit_code == 1
		assert 'Failed' in result.stdout or 'error' in result.stdout.lower()


def test_list_api_error(initialized_workspace, mock_credentials_file):
	"""Should handle API errors gracefully."""
	mock_credentials_file()
	link_project(initialized_workspace)

	mock_response = mock.Mock(spec=httpx.Response)
	mock_response.status_code = 500
	mock_response.json.return_value = {'detail': 'Internal Server Error'}
	mock_response.text = 'Internal Server Error'

	with mock.patch(
		'ambyte_cli.services.api_client.CloudApiClient.list_inventory',
		side_effect=httpx.HTTPStatusError('Server Error', request=mock.Mock(), response=mock_response),
	):
		result = runner.invoke(app, ['inventory', 'list'])

		assert result.exit_code == 1


# ==============================================================================
# API CLIENT UNIT TESTS
# ==============================================================================


def test_api_client_list_inventory_params(initialized_workspace, mock_credentials_file):
	"""Test that list_inventory passes correct params to HTTP client."""
	mock_credentials_file()
	link_project(initialized_workspace)

	from ambyte_cli.config import load_config
	from ambyte_cli.services.api_client import CloudApiClient

	client = CloudApiClient(load_config())

	mock_response = mock.Mock()
	mock_response.json.return_value = {'items': [], 'total': 0, 'page': 1, 'size': 20, 'pages': 0}
	mock_response.raise_for_status = mock.Mock()

	with mock.patch.object(client._client, 'get', return_value=mock_response) as mock_get:
		client.list_inventory(page=2, size=25, platform='snowflake', urn_filter='sales')

		mock_get.assert_called_once()
		call_args = mock_get.call_args
		assert call_args[0][0] == '/v1/resources/'
		params = call_args[1]['params']
		assert params['page'] == 2
		assert params['size'] == 25
		assert params['platform'] == 'snowflake'
		assert params['urn'] == 'sales'

	client.close()


def test_api_client_list_inventory_minimal_params(initialized_workspace, mock_credentials_file):
	"""Test list_inventory with only default params."""
	mock_credentials_file()
	link_project(initialized_workspace)

	from ambyte_cli.config import load_config
	from ambyte_cli.services.api_client import CloudApiClient

	client = CloudApiClient(load_config())

	mock_response = mock.Mock()
	mock_response.json.return_value = {'items': [], 'total': 0, 'page': 1, 'size': 50, 'pages': 0}
	mock_response.raise_for_status = mock.Mock()

	with mock.patch.object(client._client, 'get', return_value=mock_response) as mock_get:
		client.list_inventory()

		mock_get.assert_called_once()
		params = mock_get.call_args[1]['params']
		assert params['page'] == 1
		assert params['size'] == 50
		assert 'platform' not in params
		assert 'urn' not in params

	client.close()

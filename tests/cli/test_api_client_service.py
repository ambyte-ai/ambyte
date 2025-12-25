import httpx
import pytest
from unittest import mock
from ambyte_cli.services.api_client import CloudApiClient
from ambyte_cli.config import AmbyteConfig, CloudConfig

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_config():
	return AmbyteConfig(
		project_name='test-project',
		cloud=CloudConfig(url='https://api.test.ai', project_id='proj_123', organization_id='org_456'),
	)


@pytest.fixture
def api_client(mock_config, mock_credentials_file):
	# Initialize with a valid fake API key
	mock_credentials_file(api_key='sk_live_test_123')
	client = CloudApiClient(mock_config)
	return client


# ==============================================================================
# TESTS: Headers & Initialization
# ==============================================================================


def test_headers_construction(api_client):
	headers = api_client._get_headers()
	assert headers['Authorization'] == 'Bearer sk_live_test_123'
	assert headers['X-Ambyte-Project-Id'] == 'proj_123'
	assert 'ambyte-cli' in headers['User-Agent']


def test_headers_missing_key(mock_config, no_credentials):
	client = CloudApiClient(mock_config)
	headers = client._get_headers()
	assert headers == {}


# ==============================================================================
# TESTS: HTTP Error Handling (_handle_http_error)
# ==============================================================================


@pytest.mark.parametrize(
	'status_code, expected_msg',
	[
		(401, 'Authentication Failed'),
		(403, 'Permission Denied'),
		(404, 'Resource Not Found'),
		(500, 'Cloud Error (500)'),
	],
)
def test_handle_http_error_messages(api_client, status_code, expected_msg):
	# Create a dummy response
	response = httpx.Response(status_code, json={'detail': 'Something went wrong'}, request=mock.Mock())
	error = httpx.HTTPStatusError('Error', request=mock.Mock(), response=response)

	with mock.patch('ambyte_cli.services.api_client.console') as mock_console:
		api_client._handle_http_error(error)

		# Verify the printed output contains our expected string
		combined_output = ''.join(str(call) for call in mock_console.print.call_args_list)
		assert expected_msg in combined_output


# ==============================================================================
# TESTS: API Methods (Push, Pull, Sync)
# ==============================================================================


def test_push_obligations_success(api_client):
	mock_data = [{'id': 'policy-1'}]

	def handler(request):
		assert request.method == 'PUT'
		# With base_url set, the request.url will be the full path
		assert '/v1/obligations/' in str(request.url)
		return httpx.Response(200, json=[{'status': 'CREATED', 'slug': 'policy-1'}])

	# FIX: Pass base_url to the mock client
	api_client._client = httpx.Client(base_url=api_client.base_url, transport=httpx.MockTransport(handler))

	result = api_client.push_obligations(mock_data, prune=True)
	assert result[0]['status'] == 'CREATED'


def test_sync_inventory_success(api_client):
	mock_resources = [{'urn': 'urn:test'}]

	def handler(request):
		return httpx.Response(200, json=[{'urn': 'urn:test', 'id': 'uuid'}])

	api_client._client = httpx.Client(base_url=api_client.base_url, transport=httpx.MockTransport(handler))

	result = api_client.sync_inventory(mock_resources)
	assert result[0]['urn'] == 'urn:test'


def test_fetch_obligations_success(api_client):
	def handler(request):
		return httpx.Response(200, json=[{'id': 'p1'}, {'id': 'p2'}])

	api_client._client = httpx.Client(base_url=api_client.base_url, transport=httpx.MockTransport(handler))

	result = api_client.fetch_obligations()
	assert len(result) == 2


# ==============================================================================
# TESTS: Connection & Request Failures
# ==============================================================================


def test_push_obligations_network_error(api_client):
	"""Verify RequestError (DNS/Timeout) is caught and reported."""

	def handler(request):
		raise httpx.RequestError('No internet')

	api_client._client = httpx.Client(base_url=api_client.base_url, transport=httpx.MockTransport(handler))

	with mock.patch('ambyte_cli.services.api_client.console') as mock_console:
		with pytest.raises(httpx.RequestError):
			api_client.push_obligations([])

		# Ensure we logged the network error to console
		combined_output = ''.join(str(call) for call in mock_console.print.call_args_list)
		assert 'Network Error' in combined_output


def test_push_obligations_http_status_error(api_client):
	"""Verify HTTPStatusError (4xx/5xx) triggers the error handler and re-raises."""

	def handler(request):
		return httpx.Response(403, json={'detail': 'No Scope'})

	api_client._client = httpx.Client(base_url=api_client.base_url, transport=httpx.MockTransport(handler))

	with mock.patch.object(api_client, '_handle_http_error') as mock_handler:
		with pytest.raises(httpx.HTTPStatusError):
			api_client.push_obligations([])

		mock_handler.assert_called_once()


def test_close_connection(api_client):
	"""Ensure client close() propagates to internal httpx client."""
	with mock.patch.object(api_client._client, 'close') as mock_close:
		api_client.close()
		mock_close.assert_called_once()

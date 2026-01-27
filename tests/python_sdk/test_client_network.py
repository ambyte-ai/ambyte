import httpx
import pytest
from ambyte.client import AmbyteClient
from ambyte.config import reset_config
from ambyte.exceptions import AmbyteConnectionError


@pytest.fixture(autouse=True)
def clean_state():
	reset_config()
	# Also reset the Client singleton
	AmbyteClient._instance = None
	yield
	AmbyteClient._instance = None


def test_check_permission_allow():
	"""
	Happy Path: API returns ALLOW.
	"""

	# Create a transport that returns static JSON
	def handler(request):
		return httpx.Response(200, json={'allowed': True})

	client = AmbyteClient()
	# Swap the internal client transport
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	allowed = client.check_permission('urn:test', 'read')
	assert allowed is True


def test_check_permission_deny():
	"""
	Happy Path: API returns DENY.
	"""

	def handler(request):
		return httpx.Response(200, json={'allowed': False})

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	allowed = client.check_permission('urn:test', 'read')
	assert allowed is False


def test_retry_on_server_error(monkeypatch):
	"""
	Simulate a flaky server: 500, 500, 200 (ALLOW).
	Tenacity should retry and eventually succeed.
	"""
	call_count = 0

	def flaky_handler(request):
		nonlocal call_count
		call_count += 1
		if call_count < 3:
			return httpx.Response(500)
		return httpx.Response(200, json={'allowed': True})

	client = AmbyteClient()
	# We must patch the client inside the wrapper because tenacity wraps the method
	# However, tenacity wraps `check_permission`, which calls `self._client.post`.
	# So replacing `_client` is sufficient.
	client._client = httpx.Client(transport=httpx.MockTransport(flaky_handler), base_url='http://test')

	# We need to speed up the retry wait for tests to avoid slow execution
	# Tenacity has a `wait` parameter. We can't easily change the decorator args at runtime,
	# but since wait_exponential starts small, it's usually acceptable.
	# Alternatively, we can rely on unit testing tenacity configuration separately,
	# but here we just run it.

	allowed = client.check_permission('urn:test', 'read')

	assert allowed is True
	assert call_count == 3  # Initial + 2 Retries


def test_fail_open_on_connection_error():
	"""
	If the server is unreachable (ConnectError) and fail_open=True (default),
	it should return True (Allow) and log a warning.
	"""

	def network_error_handler(request):
		raise httpx.ConnectError('Connection refused')

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(network_error_handler), base_url='http://test')

	# Ensure config is set to fail_open (default)
	assert client.settings.fail_open is True

	# Should not raise exception
	allowed = client.check_permission('urn:test', 'read')

	assert allowed is True


def test_fail_closed_on_connection_error(monkeypatch):
	"""
	If fail_open=False, a connection error should raise AmbyteConnectionError.
	"""
	# 1. Force config to fail_closed
	monkeypatch.setenv('AMBYTE_FAIL_OPEN', 'false')
	reset_config()  # Reload config

	client = AmbyteClient()  # Re-init client with new config

	def network_error_handler(request):
		raise httpx.ConnectError('Connection refused')

	client._client = httpx.Client(transport=httpx.MockTransport(network_error_handler), base_url='http://test')

	with pytest.raises(AmbyteConnectionError):
		client.check_permission('urn:test', 'read')


@pytest.mark.asyncio
async def test_async_check_permission():
	"""
	Verify the async path works similarly.
	"""

	def handler(request):
		return httpx.Response(200, json={'allowed': True})

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	allowed = await client.check_permission_async('urn:async', 'write')
	assert allowed is True

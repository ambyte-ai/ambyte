import httpx
import pytest
from ambyte.client import AmbyteClient, get_client
from ambyte.config import reset_config
from ambyte.exceptions import AmbyteConnectionError


@pytest.fixture(autouse=True)
def clean_state():
	reset_config()
	# Also reset the Client singleton
	AmbyteClient._instance = None
	yield
	AmbyteClient._instance = None


# =============================================================================
# SINGLETON BEHAVIOR
# =============================================================================


def test_singleton_pattern():
	"""Verify get_instance returns the same object."""
	client1 = AmbyteClient.get_instance()
	client2 = AmbyteClient.get_instance()
	assert client1 is client2


def test_get_client_helper():
	"""Verify get_client() helper function works."""
	client = get_client()
	assert isinstance(client, AmbyteClient)
	# Should be singleton
	assert get_client() is client


# =============================================================================
# OFF MODE BYPASS
# =============================================================================


def test_should_bypass_off_mode(monkeypatch):
	"""Verify _should_bypass returns True when mode is OFF."""
	monkeypatch.setenv('AMBYTE_MODE', 'OFF')
	reset_config()
	client = AmbyteClient()
	assert client._should_bypass() is True


def test_should_bypass_remote_mode():
	"""Verify _should_bypass returns False when mode is REMOTE."""
	client = AmbyteClient()
	assert client._should_bypass() is False


def test_check_permission_off_mode(monkeypatch):
	"""Verify check_permission returns True immediately in OFF mode."""
	monkeypatch.setenv('AMBYTE_MODE', 'OFF')
	reset_config()
	client = AmbyteClient()
	# Should return True without hitting any network
	assert client.check_permission('urn:test', 'read') is True


@pytest.mark.asyncio
async def test_check_permission_async_off_mode(monkeypatch):
	"""Verify async check_permission bypasses in OFF mode."""
	monkeypatch.setenv('AMBYTE_MODE', 'OFF')
	reset_config()
	client = AmbyteClient()
	result = await client.check_permission_async('urn:test', 'read')
	assert result is True


# =============================================================================
# PERMISSION CHECKS (SYNC)
# =============================================================================


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


def test_check_permission_with_explicit_actor_and_context():
	"""Verify explicit actor_id and context are passed correctly."""
	received_payload = None

	def handler(request):
		nonlocal received_payload
		received_payload = request.read()
		return httpx.Response(200, json={'allowed': True})

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	client.check_permission('urn:data', 'write', actor_id='user_123', context={'env': 'prod'})

	import json

	payload = json.loads(received_payload)
	assert payload['actor_id'] == 'user_123'
	assert payload['context']['env'] == 'prod'


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


# =============================================================================
# PERMISSION CHECKS (ASYNC)
# =============================================================================


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


@pytest.mark.asyncio
async def test_async_check_permission_deny():
	"""Verify async returns False when API denies."""

	def handler(request):
		return httpx.Response(200, json={'allowed': False})

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	allowed = await client.check_permission_async('urn:async', 'write')
	assert allowed is False


@pytest.mark.asyncio
async def test_async_fail_open_on_error():
	"""Verify async path fails open on connection error."""

	def handler(request):
		raise httpx.ConnectError('Connection refused')

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	result = await client.check_permission_async('urn:test', 'read')
	assert result is True


# =============================================================================
# LIST OBLIGATIONS
# =============================================================================


def test_list_obligations_success():
	"""Verify list_obligations returns obligations from API."""

	def handler(request):
		assert request.url.path == '/v1/obligations/'
		return httpx.Response(200, json=[{'slug': 'policy-1'}, {'slug': 'policy-2'}])

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	result = client.list_obligations()
	assert len(result) == 2
	assert result[0]['slug'] == 'policy-1'


def test_list_obligations_with_filters():
	"""Verify query params are passed correctly."""

	def handler(request):
		assert 'enforcement_level=BLOCK' in str(request.url)
		assert 'query=gdpr' in str(request.url)
		return httpx.Response(200, json=[])

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	client.list_obligations(enforcement_level='BLOCK', query='gdpr')


def test_list_obligations_error_fail_open():
	"""Verify list_obligations returns empty list on error with fail_open."""

	def handler(request):
		raise httpx.ConnectError('Connection refused')

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	result = client.list_obligations()
	assert result == []


@pytest.mark.asyncio
async def test_list_obligations_async_success():
	"""Verify async list_obligations works."""

	def handler(request):
		return httpx.Response(200, json=[{'slug': 'async-policy'}])

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	result = await client.list_obligations_async()
	assert len(result) == 1


@pytest.mark.asyncio
async def test_list_obligations_async_with_filters():
	"""Verify async list_obligations passes filters."""

	def handler(request):
		assert 'enforcement_level=WARN' in str(request.url)
		return httpx.Response(200, json=[])

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	await client.list_obligations_async(enforcement_level='WARN')


@pytest.mark.asyncio
async def test_list_obligations_async_error():
	"""Verify async list_obligations returns empty on error."""

	def handler(request):
		raise httpx.ConnectError('Connection refused')

	client = AmbyteClient()
	client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')

	result = await client.list_obligations_async()
	assert result == []


# =============================================================================
# LOG ACCESS
# =============================================================================


def test_log_access_off_mode(monkeypatch):
	"""Verify log_access does nothing in OFF mode."""
	monkeypatch.setenv('AMBYTE_MODE', 'OFF')
	reset_config()
	client = AmbyteClient()

	# Should not raise or do anything
	client.log_access('urn:test', 'read', True)


def test_log_access_sync_fallback(monkeypatch):
	"""Verify log_access uses sync HTTP when background_sync is disabled."""
	monkeypatch.setenv('AMBYTE_ENABLE_BACKGROUND_SYNC', 'false')
	reset_config()

	received_payload = None

	def handler(request):
		nonlocal received_payload
		received_payload = request.read()
		return httpx.Response(200)

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	client.log_access('urn:data', 'write', True, actor_id='user_1')

	import json

	payload = json.loads(received_payload)
	assert 'logs' in payload
	assert payload['logs'][0]['resource_urn'] == 'urn:data'
	assert payload['logs'][0]['action'] == 'write'
	assert payload['logs'][0]['decision'] == 'ALLOW'
	assert payload['logs'][0]['actor_id'] == 'user_1'


def test_log_access_sync_error_silent(monkeypatch):
	"""Verify log_access swallows errors silently (never crashes app)."""
	monkeypatch.setenv('AMBYTE_ENABLE_BACKGROUND_SYNC', 'false')
	reset_config()

	def handler(request):
		raise httpx.ConnectError('Connection refused')

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	# Should not raise
	client.log_access('urn:data', 'read', False)


def test_log_access_background_sync(monkeypatch):
	"""Verify log_access enqueues to tracker when background_sync is enabled."""
	from unittest import mock

	monkeypatch.setenv('AMBYTE_ENABLE_BACKGROUND_SYNC', 'true')
	reset_config()

	client = AmbyteClient()

	with mock.patch('ambyte.tracking.manager.get_tracker') as mock_get_tracker:
		mock_tracker = mock.MagicMock()
		mock_get_tracker.return_value = mock_tracker

		# Need to reload the import in log_access
		with mock.patch.dict('sys.modules', {'ambyte.tracking.manager': mock.MagicMock(get_tracker=mock_get_tracker)}):
			# The import is inside log_access, so we patch it there
			with mock.patch('ambyte.tracking.manager.get_tracker', mock_get_tracker):
				client.log_access('urn:test', 'read', True)

				mock_tracker.enqueue.assert_called_once()
				call_args = mock_tracker.enqueue.call_args
				assert call_args[0][0] == 'audit'


def test_log_access_deny_decision(monkeypatch):
	"""Verify log_access correctly sets DENY decision."""
	monkeypatch.setenv('AMBYTE_ENABLE_BACKGROUND_SYNC', 'false')
	reset_config()

	received_payload = None

	def handler(request):
		nonlocal received_payload
		received_payload = request.read()
		return httpx.Response(200)

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	client.log_access('urn:data', 'delete', False)

	import json

	payload = json.loads(received_payload)
	assert payload['logs'][0]['decision'] == 'DENY'


def test_log_access_anonymous_actor(monkeypatch):
	"""Verify log_access defaults to anonymous when no actor provided."""
	monkeypatch.setenv('AMBYTE_ENABLE_BACKGROUND_SYNC', 'false')
	reset_config()

	received_payload = None

	def handler(request):
		nonlocal received_payload
		received_payload = request.read()
		return httpx.Response(200)

	client = AmbyteClient()
	client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test')

	client.log_access('urn:data', 'read', True)

	import json

	payload = json.loads(received_payload)
	assert payload['logs'][0]['actor_id'] == 'anonymous'


# =============================================================================
# CLOSE METHOD
# =============================================================================


def test_close_method():
	"""Verify close() closes sync client without error."""
	client = AmbyteClient()
	# Should not raise
	client.close()


# =============================================================================
# BUILD CHECK PAYLOAD
# =============================================================================


def test_build_check_payload_defaults():
	"""Verify _build_check_payload uses defaults correctly."""
	client = AmbyteClient()

	payload = client._build_check_payload('urn:resource', 'read', None, None)

	assert payload['resource_urn'] == 'urn:resource'
	assert payload['action'] == 'read'
	assert payload['actor_id'] == 'anonymous'
	assert payload['context'] == {}


def test_build_check_payload_with_context():
	"""Verify _build_check_payload merges context."""
	client = AmbyteClient()

	payload = client._build_check_payload('urn:resource', 'write', 'user_1', {'env': 'prod', 'region': 'us'})

	assert payload['actor_id'] == 'user_1'
	assert payload['context']['env'] == 'prod'
	assert payload['context']['region'] == 'us'


def test_build_check_payload_with_context_var_actor():
	"""Verify _build_check_payload uses actor from context var when not explicit."""
	from ambyte.context import context as ambyte_context_manager
	from ambyte_schemas.models.common import Actor, ActorType

	client = AmbyteClient()

	with ambyte_context_manager(actor=Actor(id='ctx_user', type=ActorType.HUMAN)):
		payload = client._build_check_payload('urn:resource', 'read', None, None)

	assert payload['actor_id'] == 'ctx_user'

import asyncio
from unittest import mock

import pytest
from ambyte.decorators import audit, guard
from ambyte.exceptions import AmbyteAccessDenied


@pytest.fixture
def mock_engine_async():
	with mock.patch('ambyte.decorators.get_decision_engine') as mock_get:
		engine = mock_get.return_value
		# Setup the async mock method
		engine.check_access_async = mock.AsyncMock()
		yield engine


@pytest.fixture
def mock_client():
	with mock.patch('ambyte.decorators.get_client') as mock_get:
		yield mock_get.return_value


@pytest.mark.asyncio
async def test_async_guard_allow(mock_engine_async):
	"""
	Async function should run if policy allows.
	"""
	mock_engine_async.check_access_async.return_value = True

	@guard(resource='urn:async', action='process')
	async def async_process(data):
		await asyncio.sleep(0.001)
		return f'processed {data}'

	result = await async_process('foo')

	assert result == 'processed foo'
	mock_engine_async.check_access_async.assert_awaited_once_with(
		resource_urn='urn:async', action='process', context=None
	)


@pytest.mark.asyncio
async def test_async_guard_deny(mock_engine_async):
	"""
	Async function should raise exception and NOT run if denied.
	"""
	mock_engine_async.check_access_async.return_value = False

	execution_spy = mock.Mock()

	@guard(resource='urn:secret', action='read')
	async def view_secret():
		execution_spy()
		return 'secret'

	with pytest.raises(AmbyteAccessDenied):
		await view_secret()

	execution_spy.assert_not_called()


@pytest.mark.asyncio
async def test_async_audit_logging(mock_client):
	"""
	Verify @audit works on async functions.
	"""

	@audit(resource='urn:audit', action='log')
	async def audited_func():
		return 42

	result = await audited_func()

	assert result == 42
	mock_client.log_access.assert_called_once_with('urn:audit', 'log', allowed=True)


@pytest.mark.asyncio
async def test_dynamic_resource_async(mock_engine_async):
	"""
	Verify lambda resolution works for async wrappers.
	"""
	mock_engine_async.check_access_async.return_value = True

	@guard(resource=lambda x: f'urn:data:{x}')
	async def fetch(x):
		return x

	await fetch(99)

	mock_engine_async.check_access_async.assert_awaited_once()
	args = mock_engine_async.check_access_async.call_args
	assert args.kwargs['resource_urn'] == 'urn:data:99'

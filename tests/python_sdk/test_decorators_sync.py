from unittest import mock

import pytest
from ambyte.decorators import audit, guard
from ambyte.exceptions import AmbyteAccessDenied


@pytest.fixture
def mock_engine():
	with mock.patch('ambyte.decorators.get_decision_engine') as mock_get:
		yield mock_get.return_value


@pytest.fixture
def mock_client():
	with mock.patch('ambyte.decorators.get_client') as mock_get:
		yield mock_get.return_value


def test_guard_allow_execution(mock_engine):
	"""
	If the engine returns True, the function should execute and return its result.
	"""
	mock_engine.check_access.return_value = True

	@guard(resource='urn:test', action='read')
	def sensitive_op(x, y):
		return x + y

	result = sensitive_op(5, 10)

	assert result == 15
	mock_engine.check_access.assert_called_once_with(resource_urn='urn:test', action='read', context=None)


def test_guard_deny_execution(mock_engine):
	"""
	If the engine returns False, the function should NOT execute and raise AccessDenied.
	"""
	mock_engine.check_access.return_value = False

	# Create a spy to verify execution
	execution_spy = mock.Mock()

	@guard(resource='urn:test', action='delete')
	def dangerous_op():
		execution_spy()

	with pytest.raises(AmbyteAccessDenied) as exc:
		dangerous_op()

	assert "Ambyte Policy blocked action 'delete'" in str(exc.value)
	execution_spy.assert_not_called()


def test_guard_dynamic_resource_resolution(mock_engine):
	"""
	Verify that lambda functions can resolve the resource URN from arguments.
	"""
	mock_engine.check_access.return_value = True

	@guard(resource=lambda uid: f'urn:user:{uid}', action='update')
	def update_user(uid):
		return 'updated'

	update_user(123)

	mock_engine.check_access.assert_called_once_with(resource_urn='urn:user:123', action='update', context=None)


def test_guard_dynamic_resource_failure(mock_engine):
	"""
	If the lambda fails (e.g. key error), it should default to error URN but not crash the decorator logic itself.
	"""
	mock_engine.check_access.return_value = True

	# Lambda expects 'id' in kwargs, but we won't pass it
	@guard(resource=lambda **kw: f'urn:user:{kw["id"]}')
	def broken_func(name):
		return 'ok'

	broken_func('alice')

	# Check that it fell back to the error URN
	mock_engine.check_access.assert_called_once()
	args = mock_engine.check_access.call_args
	assert args.kwargs['resource_urn'] == 'urn:ambyte:error:resolution_failed'


def test_audit_decorator_non_blocking(mock_client):
	"""
	Verify @audit logs success but doesn't block execution even if logging fails.
	"""
	# Simulate logging failure
	mock_client.log_access.side_effect = Exception('Logging unavailable')

	@audit(resource='urn:safe', action='view')
	def safe_op():
		return 'success'

	result = safe_op()

	assert result == 'success'
	mock_client.log_access.assert_called_once_with('urn:safe', 'view', allowed=True)

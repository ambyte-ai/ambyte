from unittest.mock import MagicMock, call, patch

import pytest
from ambyte_databricks.executor import SqlExecutor
from databricks.sdk.service.sql import (
	ResultData,
	ServiceError,
	StatementResponse,
	StatementState,
	StatementStatus,
)


@pytest.fixture
def mock_settings():
	with patch('ambyte_databricks.executor.settings') as s:
		s.WAREHOUSE_ID = 'wh_mock_123'
		yield s


@pytest.fixture
def executor(mock_db_client, mock_settings):
	"""
	Returns an SqlExecutor instance with a mocked WorkspaceClient
	and configured settings.
	"""
	return SqlExecutor(client=mock_db_client)


def make_response(state: StatementState, statement_id='stmt_123', error_message=None) -> StatementResponse:
	"""Helper to create a StatementResponse object."""
	error = None
	if error_message:
		error = ServiceError(message=error_message)

	status = StatementStatus(state=state, error=error)

	# Minimal result structure
	result = ResultData(chunk_index=0, row_count=1) if state == StatementState.SUCCEEDED else None

	return StatementResponse(statement_id=statement_id, status=status, result=result)


def test_init_sets_warehouse_id(mock_db_client, mock_settings):
	executor = SqlExecutor(mock_db_client)
	assert executor.warehouse_id == 'wh_mock_123'


def test_execute_missing_warehouse_id(mock_db_client):
	# Patch settings to have no warehouse ID
	with patch('ambyte_databricks.executor.settings') as s:
		s.WAREHOUSE_ID = None
		executor = SqlExecutor(mock_db_client)

		with pytest.raises(ValueError, match='Warehouse ID is not configured'):
			executor.execute('SELECT 1')


def test_execute_immediate_success(executor, mock_db_client):
	# Setup mock to return SUCCEEDED immediately
	mock_response = make_response(StatementState.SUCCEEDED)
	mock_db_client.statement_execution.execute_statement.return_value = mock_response

	result = executor.execute('CREATE TABLE foo')

	assert result == {'chunk_index': 0, 'row_count': 1}
	mock_db_client.statement_execution.execute_statement.assert_called_once_with(
		statement='CREATE TABLE foo', warehouse_id='wh_mock_123', wait_timeout='50s'
	)


def test_execute_polling_success(executor, mock_db_client):
	"""
	Test that execute polls when the initial response is RUNNING.
	"""
	# 1. First call returns RUNNING
	resp_running = make_response(StatementState.RUNNING)
	# 2. Polling call returns PENDING (just to test loop)
	resp_pending = make_response(StatementState.PENDING)
	# 3. Final call returns SUCCEEDED
	resp_success = make_response(StatementState.SUCCEEDED)

	mock_db_client.statement_execution.execute_statement.return_value = resp_running
	mock_db_client.statement_execution.get_statement.side_effect = [resp_pending, resp_success]

	with patch('ambyte_databricks.executor.time.sleep') as mock_sleep:
		result = executor.execute('LONG RUNNING QUERY')

		# Should have slept twice
		assert mock_sleep.call_count == 2

	assert result['row_count'] == 1
	# Verify we called execute once
	mock_db_client.statement_execution.execute_statement.assert_called_once()
	# Verify we polled twice with the correct ID
	assert mock_db_client.statement_execution.get_statement.call_count == 2
	mock_db_client.statement_execution.get_statement.assert_called_with('stmt_123')


def test_execute_failure(executor, mock_db_client):
	# Setup mock to return FAILED
	mock_response = make_response(StatementState.FAILED, error_message='Syntax Error')
	mock_db_client.statement_execution.execute_statement.return_value = mock_response

	with pytest.raises(Exception, match='Databricks SQL Error: Syntax Error'):
		executor.execute('BAD SQL')


def test_execute_failure_unknown_error(executor, mock_db_client):
	# Setup mock to return FAILED but with no error details
	mock_response = make_response(StatementState.FAILED, error_message=None)
	# Ensure error object is None
	mock_response.status.error = None

	mock_db_client.statement_execution.execute_statement.return_value = mock_response

	with pytest.raises(Exception, match='Databricks SQL Error: Unknown Error'):
		executor.execute('MYSTERY FAIL')


def test_execute_canceled(executor, mock_db_client):
	# Setup mock to return CANCELED
	mock_response = make_response(StatementState.CANCELED, error_message='User Canceled')
	mock_db_client.statement_execution.execute_statement.return_value = mock_response

	with pytest.raises(Exception, match='Databricks SQL Error: User Canceled'):
		executor.execute('Slow Query')


def test_execute_missing_statement_id(executor, mock_db_client):
	# Setup mock to return response with no ID
	mock_response = make_response(StatementState.RUNNING, statement_id=None)
	mock_db_client.statement_execution.execute_statement.return_value = mock_response

	with pytest.raises(ValueError, match='Databricks did not return a statement_id'):
		executor.execute('SELECT 1')


def test_execute_client_exception(executor, mock_db_client):
	"""Test that underlying SDK errors are propagated/logged."""
	mock_db_client.statement_execution.execute_statement.side_effect = Exception('Network Error')

	with pytest.raises(Exception, match='Network Error'):
		executor.execute('SELECT 1')


def test_execute_batch_success(executor):
	# Mock self.execute on the instance to avoid mocking internal SDK calls for this test
	executor.execute = MagicMock()

	stmts = ['SQL 1', '  ', 'SQL 2']  # includes empty string
	executor.execute_batch(stmts)

	# Should skip empty string
	assert executor.execute.call_count == 2
	executor.execute.assert_has_calls([call('SQL 1'), call('SQL 2')])


def test_execute_batch_failure(executor):
	executor.execute = MagicMock()
	# First succeeds, second fails
	executor.execute.side_effect = [None, Exception('Boom'), None]

	stmts = ['SQL 1', 'SQL 2', 'SQL 3']

	with pytest.raises(Exception, match='Boom'):
		executor.execute_batch(stmts)

	# Should stop after SQL 2
	assert executor.execute.call_count == 2

import logging
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from .config import settings

logger = logging.getLogger('ambyte.connector.databricks.executor')


class SqlExecutor:
	"""
	Executes SQL commands against a Databricks SQL Warehouse using the REST API.
	Handles async polling and error reporting.
	"""

	def __init__(self, client: WorkspaceClient):
		self.client = client
		self.warehouse_id = settings.WAREHOUSE_ID

	def execute(self, sql: str, timeout_seconds: int = 50) -> dict[str, Any]:
		"""
		Submits a SQL statement and waits for completion.

		Returns:
		    The raw result dictionary (manifest, schema, data array).

		Raises:
		    Exception: If the SQL execution fails in Databricks.
		"""  # noqa: E101
		if not self.warehouse_id:
			raise ValueError('Warehouse ID is not configured. Please set AMBYTE_DATABRICKS_WAREHOUSE_ID.')

		logger.debug(f'Executing SQL on Warehouse {self.warehouse_id}...')

		try:
			# 1. Submit
			response = self.client.statement_execution.execute_statement(
				statement=sql,
				warehouse_id=self.warehouse_id,
				wait_timeout=f'{timeout_seconds}s',  # Databricks format "50s"
			)

			# 2. Poll if necessary
			# If the server times out (returns 200 OK but state is RUNNING), we poll manually.
			# DDLs usually finish instantly, but this handles edge cases.
			statement_id = response.statement_id
			if not statement_id:
				raise ValueError('Databricks did not return a statement_id.')

			while not response.status or response.status.state in [StatementState.PENDING, StatementState.RUNNING]:
				logger.debug(f'Statement {statement_id} still running, polling...')
				time.sleep(1)  # Simple backoff
				response = self.client.statement_execution.get_statement(statement_id)

			# Check final state
			if response.status and response.status.state in [StatementState.FAILED, StatementState.CANCELED]:
				error_msg = response.status.error.message if response.status.error else 'Unknown Error'
				logger.error(f'SQL Execution Failed: {error_msg}')
				logger.debug(f'Failed SQL: {sql}')
				raise Exception(f'Databricks SQL Error: {error_msg}')

			logger.info('SQL executed successfully.')

			# Return results (usually empty for DDL, but good for debugging)
			return {
				'chunk_index': response.result.chunk_index if response.result else 0,
				'row_count': response.result.row_count if response.result else 0,
			}

		except Exception as e:
			logger.error(f'Executor System Error: {e}')
			raise

	def execute_batch(self, statements: list[str]):
		"""
		Runs a sequence of statements. Stops on first failure.
		"""
		for i, sql in enumerate(statements):
			if not sql.strip():
				continue
			try:
				self.execute(sql)
			except Exception as e:
				logger.error(f'Batch failed at statement #{i + 1}')
				raise e

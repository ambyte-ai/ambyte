import logging
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from ambyte_schemas.models.common import Actor, ActorType
from ambyte_schemas.models.lineage import LineageEvent, Run, RunType
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from ambyte_databricks.config import settings
from ambyte_databricks.mapper import ResourceMapper

logger = logging.getLogger('ambyte.connector.databricks.lineage')


class LineageExtractor:
	"""
	Crawls Unity Catalog System Tables to extract data lineage.

	Source: `system.access.table_lineage`
	This table captures read->write dependencies automatically tracked by Databricks.
	"""

	def __init__(self, client: WorkspaceClient):
		self.client = client
		self.mapper = ResourceMapper()  # Re-used for URN generation logic

		# We need a warehouse to query the system tables
		if not settings.WAREHOUSE_ID:
			raise ValueError('WAREHOUSE_ID is required to query system tables.')
		self.warehouse_id = settings.WAREHOUSE_ID

	def extract(self, lookback_hours: int = 24) -> Generator[tuple[Run, LineageEvent], None, None]:
		"""
		Queries the system catalog and yields (Run, LineageEvent) pairs.

		Args:
		    lookback_hours: How far back to scan for events.
		"""  # noqa: E101
		logger.info(f'Extracting lineage for the last {lookback_hours} hours...')

		safe_hours = int(lookback_hours)

		# 1. Construct Query
		# We target system.access.table_lineage
		# We limit columns to essential data to reduce IO
		sql = f"""
        SELECT
            source_table_full_name,
            target_table_full_name,
            event_time,
            created_by,
            entity_type
        FROM system.access.table_lineage
        WHERE event_time >= current_timestamp() - INTERVAL '{safe_hours}' HOURS
        ORDER BY event_time DESC
        LIMIT 10000
        """  # noqa: S608

		try:
			# 2. Execute Query
			# We iterate through the results handled by the SDK wrapper
			results = self._exec_query(sql)

			count = 0
			for row in results:
				try:
					yield self._map_row(row)
					count += 1
				except Exception as e:
					logger.warning(f'Failed to map lineage row: {e}')
					continue

			logger.info(f'Extracted {count} lineage events.')

		except Exception as e:
			logger.error(f'Lineage extraction failed: {e}')
			if 'AnalysisException' in str(e) and 'system' in str(e):
				logger.critical("System tables access failed. Ensure 'system.access' is enabled in Unity Catalog.")
			raise

	def _exec_query(self, sql: str) -> Generator[dict[str, Any], None, None]:
		"""
		Helper to execute SQL and yield dict rows.
		Handles the Statement Execution API polling mechanics.
		"""
		response = self.client.statement_execution.execute_statement(
			statement=sql, warehouse_id=self.warehouse_id, wait_timeout='30s'
		)

		# Poll if not finished immediately
		statement_id = response.statement_id
		if not statement_id:
			raise Exception('Databricks did not return a statement_id.')
		while response.status and response.status.state in [StatementState.PENDING, StatementState.RUNNING]:
			response = self.client.statement_execution.get_statement(statement_id)

		if not response.status:
			raise Exception('Query execution returned no status information.')

		if response.status.state != StatementState.SUCCEEDED:
			error_msg = 'Unknown error'
			if response.status.error and response.status.error.message:
				error_msg = response.status.error.message
			raise Exception(f'Query failed: {error_msg}')

		# Fetch chunks
		manifest = response.manifest
		result = response.result

		if not manifest or not result:
			return

		schema = manifest.schema
		if not schema or not schema.columns:
			# No columns returned (e.g. empty result set or DDL)
			return

		# Map columns, filtering out any without names (rare but type-possible)
		cols = [c.name for c in schema.columns if c.name]

		# Iterate row arrays
		chunk = result
		while True:
			if chunk.data_array:
				for row_values in chunk.data_array:
					yield dict(zip(cols, row_values, strict=True))

			if not chunk.next_chunk_internal_link:
				break

			current_idx = chunk.chunk_index or 0

			chunk = self.client.statement_execution.get_statement_result_chunk_n(statement_id, current_idx + 1)

	def _map_row(self, row: dict[str, Any]) -> tuple[Run, LineageEvent]:
		"""
		Converts a raw SQL row into Ambyte Canonical Models.
		"""

		# 1. Parse Basic Fields
		source_tbl = str(row.get('source_table_full_name') or 'unknown')
		target_tbl = str(row.get('target_table_full_name') or 'unknown')
		created_by = str(row.get('created_by') or 'unknown')

		# Robust time parsing with fallback
		raw_time = row.get('event_time')

		if isinstance(raw_time, str):
			# Parse ISO string
			event_time = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
		elif isinstance(raw_time, datetime):
			# Already an object (some connectors do this)
			event_time = raw_time
		else:
			# Fallback: Use current time if missing or None to prevent crash
			event_time = datetime.now(timezone.utc)

		# Ensure UTC timezone is set
		if event_time.tzinfo is None:
			event_time = event_time.replace(tzinfo=timezone.utc)

		# 2. Construct Deterministic Run ID
		# Since system tables aggregate events, we create a stable ID for this specific
		# data movement instance to ensure idempotency in the Ambyte DB.
		# ID = Hash(source + target + timestamp + user)
		unique_str = f'{source_tbl}|{target_tbl}|{event_time.isoformat()}|{created_by}'
		run_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_str))

		# 3. Map Actor
		actor_type = ActorType.HUMAN
		if '@' not in created_by and '-' in created_by:
			actor_type = ActorType.SERVICE_ACCOUNT
		elif created_by == 'System':
			actor_type = ActorType.SYSTEM_INTERNAL

		actor = Actor(
			id=created_by,
			type=actor_type,
			roles=[],  # Connector doesn't know roles
			attributes={'platform': 'databricks'},
		)

		# 4. Map Run Type
		ent_type = str(row.get('entity_type', '')).upper()
		run_type = RunType.ETL_TRANSFORM  # Default
		if 'NOTEBOOK' in ent_type:
			run_type = RunType.ETL_TRANSFORM  # Notebooks usually do ETL
		elif 'DASHBOARD' in ent_type or 'QUERY' in ent_type:
			run_type = RunType.HUMAN_DOWNLOAD  # Queries usually imply viewing

		# 5. Create Run Object
		run = Run(
			id=run_id,
			type=run_type,
			triggered_by=actor,
			start_time=event_time,  # Lineage log time is usually completion time
			end_time=event_time,
			success=True,  # If it's in lineage, data moved successfully
		)

		# 6. Create Lineage Event
		# Convert table names to Ambyte URNs
		# We reuse the ResourceMapper helper logic, but need to construct a mock asset object
		# or just use the logic directly.
		# URN format: urn:databricks:<workspace>:<table_full_name>

		# Assuming mapper has cached workspace_id
		ws_id = self.mapper._workspace_id

		def to_urn(tbl: str) -> str:
			return f'urn:databricks:{ws_id}:{tbl}'.lower()

		event = LineageEvent(run_id=run_id, input_urns=[to_urn(source_tbl)], output_urns=[to_urn(target_tbl)])

		return run, event

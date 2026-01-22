import logging
from dataclasses import dataclass, field

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import DatabricksError

from .config import settings

logger = logging.getLogger('ambyte.connector.databricks.state')


@dataclass
class GovernanceFunction:
	"""Represents an existing SQL UDF in Databricks."""

	full_name: str  # catalog.schema.name
	definition: str  # The SQL body (for diffing)
	comment: str  # Contains metadata/hash from compiler


@dataclass
class TableBinding:
	"""Represents the current policy attachment on a table."""

	full_table_name: str
	row_filter_func: str | None = None
	column_masks: dict[str, str] = field(default_factory=dict)  # col_name -> func_name


class GovernanceState:
	"""
	Reads the current state of policies in Unity Catalog.
	Used to determine if SQL updates are necessary (Idempotency/Diffing).
	"""

	def __init__(self, client: WorkspaceClient):
		self.client = client
		self.catalog = settings.GOVERNANCE_CATALOG
		self.schema = settings.GOVERNANCE_SCHEMA

		# Cache
		self._functions: dict[str, GovernanceFunction] = {}
		self._loaded = False

	def refresh(self):
		"""Fetches all governance functions from the dedicated schema."""
		self._functions.clear()

		full_schema_name = f'{self.catalog}.{self.schema}'
		logger.info(f'Fetching governance state from {full_schema_name}...')

		try:
			# 1. List Functions
			# We list functions in the specific governance schema.
			# NOTE: Databricks SDK 'functions.list' returns FunctionInfo objects.
			functions = self.client.functions.list(self.catalog, self.schema)

			for fn in functions:
				# We fetch details to get the routine definition (SQL body)
				# This might require a separate GET call if list() is shallow,
				# but usually TableInfo/FunctionInfo is sufficient for basic existence.
				# To get the full body for diffing, we might need 'get'. # TODO: Verify
				try:
					if not fn.full_name:
						continue
					full_fn = self.client.functions.get(fn.full_name)

					self._functions[fn.full_name] = GovernanceFunction(
						full_name=full_fn.full_name or fn.full_name,
						definition=full_fn.routine_definition or '',
						comment=full_fn.comment or '',
					)
				except DatabricksError as e:
					logger.warning(f'Could not fetch details for function {fn.full_name}: {e}')

			logger.info(f'Found {len(self._functions)} existing governance functions.')
			self._loaded = True

		except DatabricksError as e:
			# If schema doesn't exist, that's fine (State is empty)
			if 'SCHEMA_NOT_FOUND' in str(e) or 'NOT_FOUND' in str(e):
				logger.info('Governance schema does not exist yet. State is empty.')
				self._functions = {}
				self._loaded = True
			else:
				logger.error(f'Failed to refresh state: {e}')
				raise

	def get_function(self, name: str) -> GovernanceFunction | None:
		if not self._loaded:
			self.refresh()

		# Name might be short "mask_email" or full "main.gov.mask_email"
		# We try strict match first, then suffix match
		if name in self._functions:
			return self._functions[name]

		full_name = f'{self.catalog}.{self.schema}.{name}'
		return self._functions.get(full_name)

	def get_table_binding(self, table_name: str) -> TableBinding | None:
		"""
		Queries table metadata to find active Row Filters and Column Masks.
		"""
		try:
			# We assume table_name is fully qualified: cat.sch.tab
			table = self.client.tables.get(table_name)

			binding = TableBinding(full_table_name=table.full_name or table_name)

			# 1. Check Row Filter
			# Unity Catalog returns this in table properties or specific fields depending on API version
			if table.row_filter:
				binding.row_filter_func = table.row_filter.function_name

			# 2. Check Column Masks
			if table.columns:
				for col in table.columns:
					if col.mask and col.name:
						binding.column_masks[col.name] = col.mask.function_name or ''

			return binding

		except DatabricksError as e:
			logger.debug(f'Could not fetch bindings for {table_name}: {e}')
			return None

import logging
import re
from dataclasses import dataclass, field

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import DatabricksError

from ambyte_databricks.config import settings

logger = logging.getLogger('ambyte.connector.databricks.state')

# Regex to extract the Ambyte content hash from function comments
# Format: 'ambyte:v1:abc123ef | User comment here'
CONTENT_HASH_PATTERN = re.compile(r'^(ambyte:v\d+:[a-f0-9]+)')


@dataclass
class GovernanceFunction:
	"""Represents an existing SQL UDF in Databricks."""

	full_name: str  # catalog.schema.name
	definition: str  # The SQL body (not used for diffing due to reformatting)
	comment: str  # Contains metadata/hash from compiler

	@property
	def content_hash(self) -> str | None:
		"""
		Extracts the Ambyte content hash from the comment field.

		Returns:
		    The hash string (e.g., 'ambyte:v1:a3f8c2d1') or None if not found.
		"""  # noqa: E101
		if not self.comment:
			return None
		match = CONTENT_HASH_PATTERN.match(self.comment)
		return match.group(1) if match else None


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
				if not fn.full_name:
					continue

				# OPTIMIZATION: Try to get definition from the list object first.
				# Only perform a secondary GET if the definition is unexpectedly missing.
				definition = fn.routine_definition
				comment = fn.comment

				if definition is None:
					logger.debug(f'Definition missing in list for {fn.full_name}, fetching details...')
					try:
						full_fn = self.client.functions.get(fn.full_name)
						definition = full_fn.routine_definition
						comment = full_fn.comment
					except DatabricksError as e:
						logger.warning(f'Could not fetch details for function {fn.full_name}: {e}')
						continue

				self._functions[fn.full_name] = GovernanceFunction(
					full_name=fn.full_name,
					definition=definition or '',
					comment=comment or '',
				)

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

	def needs_update(self, func_name: str, new_content_hash: str) -> bool:
		"""
		Determines if a function needs to be updated based on content hash comparison.

		This avoids false-positive change detection caused by Databricks reformatting
		the routine_definition (whitespace, capitalization, qualifiers, etc.).

		Args:
		    func_name: Fully qualified function name.
		    new_content_hash: The hash from the newly generated SQL (e.g., 'ambyte:v1:abc123').

		Returns:
		    True if the function should be updated (doesn't exist or hash differs).
		"""  # noqa: E101
		existing = self.get_function(func_name)

		if not existing:
			logger.debug(f'Function {func_name} does not exist, update needed.')
			return True

		existing_hash = existing.content_hash

		if not existing_hash:
			# Function exists but has no Ambyte hash (legacy or manual creation)
			# We should update it to add proper tracking
			logger.debug(f'Function {func_name} has no content hash, update needed.')
			return True

		if existing_hash != new_content_hash:
			logger.debug(f'Function {func_name} hash mismatch: {existing_hash} != {new_content_hash}')
			return True

		logger.debug(f'Function {func_name} is up-to-date (hash: {existing_hash})')
		return False

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

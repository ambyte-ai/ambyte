import hashlib
import logging
import re
from pathlib import Path

from ambyte_compiler.service import PolicyCompilerService
from ambyte_schemas.models.artifact import PolicyBundle
from ambyte_schemas.models.inventory import ResourceCreate

from ambyte_databricks.config import settings
from ambyte_databricks.executor import SqlExecutor
from ambyte_databricks.groups import GroupMapper
from ambyte_databricks.state import GovernanceState

logger = logging.getLogger('ambyte.connector.databricks.enforcer')


class PolicyEnforcer:
	"""
	Orchestrates the reconciliation of Databricks Unity Catalog state
	with the compiled Ambyte Policies.

	Flow:
	1. Initialize Compiler & Executor.
	2. Sync Governance Schema (Ensure it exists).
	3. Iterate Resources -> Compile UDFs -> Diff -> Apply (CREATE FUNCTION).
	4. Iterate Resources -> Compile Bindings -> Diff -> Apply (ALTER TABLE).
	"""

	def __init__(self, executor: SqlExecutor, state_manager: GovernanceState):
		self.executor = executor
		self.state = state_manager

		# Locate templates relative to the package installation or CWD
		# This assumes standard ambyte-platform directory structure or pip install
		# Fallback to local 'policy-library' if running in dev
		current_file = Path(__file__).resolve()
		base_path = current_file.parent.parent.parent.parent / 'policy-library' / 'sql_templates'
		if not base_path.exists():
			# Try standard install location if package
			# We use the current file's parent because ambyte_databricks is a namespace package
			# and might not have a __file__ attribute.
			base_path = current_file.parent / 'templates'

		if not base_path.exists():
			raise FileNotFoundError(f'Could not locate SQL templates at {base_path}')

		self.compiler = PolicyCompilerService(templates_path=base_path)
		self.group_mapper = GroupMapper()

	def enforce(self, bundle: PolicyBundle, inventory: list[ResourceCreate], dry_run: bool = False):
		"""
		Main entry point for enforcement.
		"""
		logger.info(f'Starting Enforcement (Dry Run: {dry_run})')

		# 1. Ensure Metadata is Fresh
		self.state.refresh()

		# 2. Ensure Governance Schema
		schema_sql = f'CREATE SCHEMA IF NOT EXISTS {settings.GOVERNANCE_CATALOG}.{settings.GOVERNANCE_SCHEMA}'
		if not dry_run:
			self.executor.execute(schema_sql)
		else:
			logger.info(f'[Dry Run] {schema_sql}')

		# 3. Process each resource
		for resource in inventory:
			try:
				self._reconcile_resource(resource, bundle, dry_run)
			except Exception as e:
				logger.error(f'Failed to enforce policy on {resource.urn}: {e}')
				# Continue to next resource (best effort)

	def _reconcile_resource(self, resource: ResourceCreate, bundle: PolicyBundle, dry_run: bool):
		"""
		Handles UDF creation and binding for a single table.
		"""
		policy = bundle.policies.get(resource.urn)
		if not policy:
			logger.debug(f'No active policy for {resource.urn}. Skipping.')
			return

		# Extract table metadata
		# URN format: urn:databricks:workspace:catalog.schema.table
		parts = resource.urn.split(':')
		full_table_name = parts[-1]  # catalog.schema.table

		# Resolve Groups from Policy
		allowed_groups = []
		if policy.purpose:
			allowed_groups = self.group_mapper.resolve_groups(list(policy.purpose.allowed_purposes))

		columns = resource.attributes.get('columns', [])
		table_tags = resource.attributes.get('tags', {})

		# ======================================================================
		# PART A: ROW FILTERS
		# ======================================================================
		if policy.purpose or policy.geofencing:
			# We need a function name. Convention: ambyte_row_filter_<table_hash>
			# Hashing the table name keeps function names short and stable.
			table_hash = hashlib.sha256(full_table_name.encode()).hexdigest()[:8]
			func_name = f'{settings.GOVERNANCE_CATALOG}.{settings.GOVERNANCE_SCHEMA}.rf_{table_hash}'

			# Find the row filter reference column using tag-based detection
			ref_col_info = self._find_rls_column(columns, table_tags)

			if ref_col_info:
				ref_col_name = ref_col_info['name']
				ref_col_type = ref_col_info.get('type', 'STRING')

				assert self.compiler.databricks_gen is not None
				udf_sql = self.compiler.databricks_gen.generate_row_filter_udf(
					policy_name=func_name,
					ref_column=ref_col_name,
					input_type=ref_col_type,
					allowed_groups=allowed_groups,
					comment=f'Ambyte Row Filter for {full_table_name}',
				)

				self._apply_udf(func_name, udf_sql, dry_run)

				# Bind UDF to Table
				current_binding = self.state.get_table_binding(full_table_name)

				if not current_binding or current_binding.row_filter_func != func_name:
					bind_sql = f'ALTER TABLE {full_table_name} SET ROW FILTER {func_name} ON ({ref_col_name})'
					if not dry_run:
						self.executor.execute(bind_sql)
						logger.info(f'Applied Row Filter to {full_table_name}')
					else:
						logger.info(f'[Dry Run] {bind_sql}')
			else:
				logger.warning(
					f'No suitable RLS column found for {full_table_name}. '
					'Apply tag "ambyte.row_filter_column" or "governance.rls_key" to enable row filtering.'
				)

		# ======================================================================
		# PART B: COLUMN MASKS
		# ======================================================================
		if policy.privacy:
			sensitive_cols = self._find_sensitive_columns(columns)

			for col in sensitive_cols:
				col_name = col['name']
				col_type = col.get('type', 'STRING')

				# Name: ambyte_mask_<method>_<type_hash> to allow reuse across tables
				method_slug = policy.privacy.method.name.lower()
				type_slug = col_type.replace('<', '_').replace('>', '_').replace(',', '_')
				func_name = f'{settings.GOVERNANCE_CATALOG}.{settings.GOVERNANCE_SCHEMA}.mask_{method_slug}_{type_slug}'

				assert self.compiler.databricks_gen is not None
				udf_sql = self.compiler.databricks_gen.generate_masking_udf(
					policy_name=func_name,
					input_type=col_type,
					method=policy.privacy.method,
					allowed_groups=allowed_groups,
					comment=f'Ambyte {policy.privacy.method.name} Mask',
				)

				self._apply_udf(func_name, udf_sql, dry_run)

				# Bind UDF
				current_binding = self.state.get_table_binding(full_table_name)
				current_mask = current_binding.column_masks.get(col_name) if current_binding else None

				if current_mask != func_name:
					bind_sql = f'ALTER TABLE {full_table_name} ALTER COLUMN {col_name} SET MASK {func_name}'
					if not dry_run:
						self.executor.execute(bind_sql)
						logger.info(f'Applied Mask to {full_table_name}.{col_name}')
					else:
						logger.info(f'[Dry Run] {bind_sql}')

	# ==========================================================================
	# TAG-BASED COLUMN DETECTION
	# ==========================================================================

	# Standard governance tag keys (should match databricks_mappings.yaml)
	_TAG_ROW_FILTER_COLUMN = 'ambyte.row_filter_column'
	_TAG_RLS_KEY = 'governance.rls_key'
	_TAG_PII_CATEGORY = 'governance.pii_category'
	_TAG_IS_SENSITIVE = 'governance.is_sensitive'

	# Fallback heuristics when tags are not present
	_FALLBACK_RLS_COLUMN_NAMES = {'region', 'country', 'geo', 'tenant_id', 'org_id', 'department'}
	_FALLBACK_PII_PATTERNS = {'email', 'phone', 'ssn', 'social_security', 'credit_card', 'passport'}

	def _find_rls_column(self, columns: list[dict], table_tags: dict[str, str]) -> dict | None:
		"""
		Finds the column to use for row-level security filtering.

		Priority:
		1. Table-level tag 'ambyte.row_filter_column' specifying column name
		2. Column-level tag 'governance.rls_key' = 'true'
		3. Heuristic: Column named 'region', 'country', 'geo', etc.

		Returns:
		    Column dict with 'name' and 'type', or None if not found.
		"""  # noqa: E101
		# 1. Check table-level tag for explicit column name
		if self._TAG_ROW_FILTER_COLUMN in table_tags:
			rls_col_name = table_tags[self._TAG_ROW_FILTER_COLUMN]
			for col in columns:
				if col.get('name') == rls_col_name:
					logger.debug(f'RLS column from table tag: {rls_col_name}')
					return col
			logger.warning(
				f"Table tag '{self._TAG_ROW_FILTER_COLUMN}' specifies column '{rls_col_name}' "
				'but column not found in schema.'
			)

		# 2. Check column-level tags for governance.rls_key = 'true'
		for col in columns:
			col_tags = col.get('tags', {})
			if col_tags.get(self._TAG_RLS_KEY, '').lower() == 'true':
				logger.debug(f'RLS column from column tag: {col.get("name")}')
				return col

		# 3. Fallback to heuristic column names
		for col in columns:
			col_name = col.get('name', '')
			if col_name.lower() in self._FALLBACK_RLS_COLUMN_NAMES:
				logger.debug(f'RLS column from heuristic: {col_name}')
				return col

		return None

	def _find_sensitive_columns(self, columns: list[dict]) -> list[dict]:
		"""
		Finds columns that should be masked based on tags or heuristics.

		Priority:
		1. Column-level tag 'governance.is_sensitive' = 'true'
		2. Column-level tag 'governance.pii_category' present
		3. Heuristic: Column name contains 'email', 'ssn', 'phone', etc.

		Returns:
		    List of column dicts that should be masked.
		"""  # noqa: E101
		sensitive = []

		for col in columns:
			col_name = col.get('name', '')
			col_tags = col.get('tags', {})

			# 1. Check is_sensitive tag
			if col_tags.get(self._TAG_IS_SENSITIVE, '').lower() == 'true':
				logger.debug(f'Sensitive column from is_sensitive tag: {col_name}')
				sensitive.append(col)
				continue

			# 2. Check pii_category tag
			if self._TAG_PII_CATEGORY in col_tags:
				logger.debug(f'Sensitive column from pii_category tag: {col_name}')
				sensitive.append(col)
				continue

			# 3. Fallback to heuristic name matching
			col_name_lower = col_name.lower()
			if any(pattern in col_name_lower for pattern in self._FALLBACK_PII_PATTERNS):
				logger.debug(f'Sensitive column from heuristic: {col_name}')
				sensitive.append(col)

		return sensitive

	# Regex to extract content hash from generated SQL comment
	# Matches: COMMENT 'ambyte:v1:abc123ef | ...'
	_COMMENT_HASH_PATTERN = re.compile(r"COMMENT\s+'(ambyte:v\d+:[a-f0-9]+)")

	def _apply_udf(self, func_name: str, sql: str, dry_run: bool):
		"""
		Idempotent creation of a UDF.
		Uses content hash comparison to avoid unnecessary re-deployments.
		"""
		# Extract content hash from the generated SQL
		new_hash = self._extract_content_hash(sql)

		if not new_hash:
			# Fallback: If no hash found in SQL, always update (shouldn't happen with new generator)
			logger.warning(f'No content hash found in generated SQL for {func_name}, forcing update.')
			should_update = True
		else:
			# Use hash-based comparison to determine if update is needed
			should_update = self.state.needs_update(func_name, new_hash)

		if should_update:
			if not dry_run:
				self.executor.execute(sql)
				logger.info(f'Updated function {func_name}')
			else:
				logger.info(f'[Dry Run] Create/Update UDF {func_name}')
		else:
			logger.debug(f'Function {func_name} is up-to-date, skipping.')

	def _extract_content_hash(self, sql: str) -> str | None:
		"""Extracts the Ambyte content hash from the generated SQL's COMMENT clause."""
		match = self._COMMENT_HASH_PATTERN.search(sql)
		return match.group(1) if match else None

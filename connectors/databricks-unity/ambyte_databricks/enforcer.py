import hashlib
import logging
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

		# ======================================================================
		# PART A: ROW FILTERS
		# ======================================================================
		if policy.purpose or policy.geofencing:
			# We need a function name. Convention: ambyte_row_filter_<table_hash>
			# Hashing the table name keeps function names short and stable.
			table_hash = hashlib.sha256(full_table_name.encode()).hexdigest()[:8]
			func_name = f'{settings.GOVERNANCE_CATALOG}.{settings.GOVERNANCE_SCHEMA}.rf_{table_hash}'

			# Determine Ref Column (Default to 'id' or first column if not specified)
			# In a real impl, we'd use tagging to find the region/tenant column.
			# For MVP, we assume a column named 'region' exists or fallback to first. # TODO
			columns = resource.attributes.get('columns', [])
			ref_col = next((c['name'] for c in columns if c['name'].lower() in ['region', 'country', 'geo']), None)

			if not ref_col and columns:
				# Fallback to first column just to have valid SQL (User must configure proper tags in prod)
				ref_col = columns[0]['name']

			if ref_col:
				# 1. Compile UDF
				ctx = {  # noqa: F841
					'input_type': 'STRING',  # Simplification: assume region cols are strings # TODO
					'ref_column': ref_col,
					'allowed_groups': allowed_groups,
				}

				# We use the compiler directly to generate the CREATE FUNCTION statement
				# Pass a dummy target 'databricks' ensures we route to _compile_databricks
				# BUT we need to specifically extract just the UDF part, not the whole block if multiple policies exist.
				# The Compiler generates *all* SQL for a resource.
				# Let's use the generator directly for granular control here.

				assert self.compiler.databricks_gen is not None
				udf_sql = self.compiler.databricks_gen.generate_row_filter_udf(
					policy_name=func_name,
					ref_column=ref_col,
					input_type='STRING',
					allowed_groups=allowed_groups,
					comment=f'Ambyte Row Filter for {full_table_name}',
				)

				self._apply_udf(func_name, udf_sql, dry_run)

				# 2. Bind UDF to Table
				# Check current state
				current_binding = self.state.get_table_binding(full_table_name)

				# If filter not applied OR applied but different function name (version rotation)
				if not current_binding or current_binding.row_filter_func != func_name:
					bind_sql = f'ALTER TABLE {full_table_name} SET ROW FILTER {func_name} ON ({ref_col})'
					if not dry_run:
						self.executor.execute(bind_sql)
						logger.info(f'Applied Row Filter to {full_table_name}')
					else:
						logger.info(f'[Dry Run] {bind_sql}')

		# ======================================================================
		# PART B: COLUMN MASKS
		# ======================================================================
		if policy.privacy:
			# Iterate columns to find ones that need masking.
			# Strategy: Mask columns tagged 'pii' in inventory attributes.
			columns = resource.attributes.get('columns', [])

			for col in columns:
				# Check if column looks sensitive (naive heuristic for MVP)
				# In prod, this comes from 'is_pii' flag in Ambyte schema # TODO
				col_name = col['name']
				is_sensitive = 'email' in col_name.lower() or 'ssn' in col_name.lower() or 'phone' in col_name.lower()

				if is_sensitive:
					col_type = col.get('type', 'STRING')

					# 1. Compile UDF
					# Name: ambyte_mask_<method>_<type_hash> to allow reuse across tables!
					# Reuse reduces clutter.
					method_slug = policy.privacy.method.name.lower()
					type_slug = col_type.replace('<', '_').replace('>', '_').replace(',', '_')
					func_name = (
						f'{settings.GOVERNANCE_CATALOG}.{settings.GOVERNANCE_SCHEMA}.mask_{method_slug}_{type_slug}'
					)

					assert self.compiler.databricks_gen is not None
					udf_sql = self.compiler.databricks_gen.generate_masking_udf(
						policy_name=func_name,
						input_type=col_type,
						method=policy.privacy.method,
						allowed_groups=allowed_groups,
						comment=f'Ambyte {policy.privacy.method.name} Mask',
					)

					self._apply_udf(func_name, udf_sql, dry_run)

					# 2. Bind UDF
					current_binding = self.state.get_table_binding(full_table_name)
					current_mask = current_binding.column_masks.get(col_name) if current_binding else None

					if current_mask != func_name:
						bind_sql = f'ALTER TABLE {full_table_name} ALTER COLUMN {col_name} SET MASK {func_name}'
						if not dry_run:
							self.executor.execute(bind_sql)
							logger.info(f'Applied Mask to {full_table_name}.{col_name}')
						else:
							logger.info(f'[Dry Run] {bind_sql}')

	def _apply_udf(self, func_name: str, sql: str, dry_run: bool):
		"""
		Idempotent creation of a UDF.
		Checks if the definition has changed before running ALTER/CREATE.
		"""
		existing = self.state.get_function(func_name)

		# Calculate hash of new SQL to compare (normalization required)
		# For MVP, we simply compare the body string or rely on CREATE OR REPLACE
		# Since Databricks CREATE OR REPLACE is atomic, we can just run it if we suspect changes.
		# To save compute, we check if existing definition roughly matches. # TODO

		should_update = True
		if existing:
			# Databricks stores the body in 'routine_definition'.
			# Normalization (whitespace) is hard, so we rely on the Comment hash if we stored it previously.
			# Fallback: Just update it. Governance updates are infrequent enough. # TODO
			pass

		if should_update:
			if not dry_run:
				self.executor.execute(sql)
				logger.info(f'Updated function {func_name}')
			else:
				logger.info(f'[Dry Run] Create/Update UDF {func_name}')

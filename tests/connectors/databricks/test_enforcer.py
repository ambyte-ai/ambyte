import hashlib
from unittest.mock import MagicMock, patch

import pytest
from ambyte_databricks.enforcer import PolicyEnforcer
from ambyte_databricks.executor import SqlExecutor
from ambyte_databricks.state import GovernanceState, TableBinding
from ambyte_rules.models import (
	ConflictTrace,
	EffectivePrivacy,
	EffectivePurpose,
	ResolvedPolicy,
)
from ambyte_schemas.models.artifact import BuildMetadata, PolicyBundle
from ambyte_schemas.models.inventory import ResourceCreate
from ambyte_schemas.models.obligation import PrivacyMethod


@pytest.fixture
def mock_executor():
	return MagicMock(spec=SqlExecutor)


@pytest.fixture
def mock_state():
	state = MagicMock(spec=GovernanceState)
	state.get_table_binding.return_value = None  # Default no binding
	return state


@pytest.fixture
def mock_compiler_service():
	with patch('ambyte_databricks.enforcer.PolicyCompilerService') as cls:
		service_instance = cls.return_value
		# Mock databricks_gen
		service_instance.databricks_gen = MagicMock()
		service_instance.databricks_gen.generate_row_filter_udf.return_value = (
			"CREATE OR REPLACE FUNCTION ... COMMENT 'ambyte:v1:abcdef12'"
		)
		service_instance.databricks_gen.generate_masking_udf.return_value = (
			"CREATE OR REPLACE FUNCTION ... COMMENT 'ambyte:v1:deadbeef'"
		)
		yield service_instance


@pytest.fixture
def mock_group_mapper():
	with patch('ambyte_databricks.enforcer.GroupMapper') as cls:
		mapper = cls.return_value
		mapper.resolve_groups.return_value = ['group_a', 'group_b']
		yield mapper


@pytest.fixture
def mock_settings():
	with patch('ambyte_databricks.enforcer.settings') as s:
		s.GOVERNANCE_CATALOG = 'gov_cat'
		s.GOVERNANCE_SCHEMA = 'gov_schema'
		yield s


@pytest.fixture
def enforcer(mock_executor, mock_state, mock_compiler_service, mock_group_mapper, mock_settings):
	# Mock file system check for templates to pass __init__
	with patch('ambyte_databricks.enforcer.Path.exists', return_value=True):
		return PolicyEnforcer(mock_executor, mock_state)


# ==============================================================================
# Initialization
# ==============================================================================


def test_init_fails_if_templates_missing():
	mock_executor = MagicMock()
	mock_state = MagicMock()

	# Force exists() to return False
	with patch('ambyte_databricks.enforcer.Path.exists', return_value=False):
		with pytest.raises(FileNotFoundError, match='Could not locate SQL templates'):
			# We also need to patch PolicyCompilerService to not blow up if we pass it bad paths,
			# but init raises before creating compiler if path is missing.
			PolicyEnforcer(mock_executor, mock_state)


def test_init_success(enforcer):
	assert enforcer.compiler is not None
	assert enforcer.group_mapper is not None


# ==============================================================================
# Main Enforce Loop
# ==============================================================================


def test_enforce_basic_flow(enforcer, mock_executor, mock_state):
	bundle = PolicyBundle(policies={}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0'))
	inventory = []

	# Execute
	enforcer.enforce(bundle, inventory, dry_run=False)

	# Verify State Refresh
	mock_state.refresh.assert_called_once()

	# Verify Schema Creation
	mock_executor.execute.assert_any_call('CREATE SCHEMA IF NOT EXISTS gov_cat.gov_schema')


def test_enforce_dry_run(enforcer, mock_executor, mock_state):
	bundle = PolicyBundle(policies={}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0'))
	inventory = []

	enforcer.enforce(bundle, inventory, dry_run=True)

	# Should refresh state? yes
	mock_state.refresh.assert_called_once()

	# Should NOT execute SQL
	mock_executor.execute.assert_not_called()


def test_enforce_continues_on_error(enforcer, mock_executor):
	"""Ensure failure on one resource doesn't stop others."""
	# Create two resources
	res1 = ResourceCreate(urn='urn:1', platform='databricks', name='t1', attributes={})
	res2 = ResourceCreate(urn='urn:2', platform='databricks', name='t2', attributes={})

	bundle = PolicyBundle(policies={}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0'))

	# Patch _reconcile_resource to fail for first one
	with patch.object(enforcer, '_reconcile_resource', side_effect=[Exception('Boom'), None]) as mock_rec:
		enforcer.enforce(bundle, [res1, res2])

		assert mock_rec.call_count == 2
		# Executor should have still set up schema
		mock_executor.execute.assert_called()


# ==============================================================================
# Reconcile Logic - Row Filters
# ==============================================================================


def test_reconcile_row_filter_apply(enforcer, mock_executor, mock_state, mock_compiler_service):
	urn = 'urn:databricks:ws:cat.schema.table'

	# Policy with Purpose -> Row Filter
	reason = ConflictTrace(
		winning_obligation_id='pol-1',
		winning_source_id='src-1',
		description='Test Policy',
	)
	policy = ResolvedPolicy(
		resource_urn=urn,
		purpose=EffectivePurpose(
			allowed_purposes={'MARKETING'},
			reason=reason,
		),
	)
	bundle = PolicyBundle(
		policies={urn: policy}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0')
	)

	# Resource with suitable column
	columns = [{'name': 'country', 'type': 'STRING'}]
	res = ResourceCreate(urn=urn, platform='databricks', name='table', attributes={'columns': columns})

	# State says update needed
	mock_state.needs_update.return_value = True
	# Binding missing
	mock_state.get_table_binding.return_value = None

	# Execute
	enforcer.enforce(bundle, [res], dry_run=False)

	# 1. Verify UDF Generation
	mock_compiler_service.databricks_gen.generate_row_filter_udf.assert_called_once()

	# 2. Verify UDF Execution (Creation)
	# Check that execute was called with the SQL returned by generator
	# The generator mock returns "CREATE ... rowhash", so look for that
	create_calls = [c for c in mock_executor.execute.call_args_list if 'CREATE' in str(c)]
	assert len(create_calls) >= 1

	# 3. Verify Table Binding
	# Expected func name: gov_cat.gov_schema.rf_<hash>
	# Hash of "cat.schema.table"
	table_hash = hashlib.sha256(b'cat.schema.table').hexdigest()[:8]
	expected_func = f'gov_cat.gov_schema.rf_{table_hash}'

	bind_calls = [c for c in mock_executor.execute.call_args_list if 'ALTER TABLE' in str(c)]
	assert len(bind_calls) >= 1
	bind_sql = bind_calls[0][0][0]
	assert f'SET ROW FILTER {expected_func} ON (country)' in bind_sql


def test_reconcile_row_filter_idempotent(enforcer, mock_executor, mock_state):
	urn = 'urn:databricks:ws:cat.schema.table'
	reason = ConflictTrace(
		winning_obligation_id='pol-1',
		winning_source_id='src-1',
		description='Test Policy',
	)
	policy = ResolvedPolicy(
		resource_urn=urn,
		purpose=EffectivePurpose(
			allowed_purposes={'MARKETING'},
			reason=reason,
		),
	)
	bundle = PolicyBundle(
		policies={urn: policy}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0')
	)

	columns = [{'name': 'country', 'type': 'STRING'}]
	res = ResourceCreate(urn=urn, platform='databricks', name='table', attributes={'columns': columns})

	# Setup State: UDF is up to date, Binding matches
	mock_state.needs_update.return_value = False

	table_hash = hashlib.sha256(b'cat.schema.table').hexdigest()[:8]
	func_name = f'gov_cat.gov_schema.rf_{table_hash}'

	current_binding = TableBinding(full_table_name='cat.schema.table', row_filter_func=func_name)
	mock_state.get_table_binding.return_value = current_binding

	# Execute
	enforcer.enforce(bundle, [res], dry_run=False)

	# Should create schema only (always runs), but no UDF create or Alter Table
	# Filter calls to exclude schema creation
	calls = [c for c in mock_executor.execute.call_args_list if 'CREATE SCHEMA' not in str(c)]
	assert len(calls) == 0


def test_reconcile_no_rls_column_warning(enforcer, mock_executor, caplog):
	urn = 'urn:databricks:ws:cat.schema.table'
	reason = ConflictTrace(
		winning_obligation_id='pol-1',
		winning_source_id='src-1',
		description='Test Policy',
	)
	policy = ResolvedPolicy(
		resource_urn=urn,
		purpose=EffectivePurpose(
			allowed_purposes={'MKT'},
			reason=reason,
		),
	)
	bundle = PolicyBundle(
		policies={urn: policy}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0')
	)

	# No heuristic columns (e.g. only 'data', 'value')
	columns = [{'name': 'data', 'type': 'STRING'}]
	res = ResourceCreate(urn=urn, platform='databricks', name='table', attributes={'columns': columns})

	enforcer.enforce(bundle, [res])

	assert 'No suitable RLS column found' in caplog.text
	# Should not generate UDF
	enforcer.compiler.databricks_gen.generate_row_filter_udf.assert_not_called()


# ==============================================================================
# Reconcile Logic - Column Masks
# ==============================================================================


def test_reconcile_masking_apply(enforcer, mock_executor, mock_state, mock_compiler_service):
	urn = 'urn:databricks:ws:cat.schema.table'

	# Policy with Privacy -> Mask
	reason = ConflictTrace(
		winning_obligation_id='pol-1',
		winning_source_id='src-1',
		description='Test Policy',
	)
	policy = ResolvedPolicy(
		resource_urn=urn,
		privacy=EffectivePrivacy(
			method=PrivacyMethod.ANONYMIZATION,
			reason=reason,
		),
	)
	bundle = PolicyBundle(
		policies={urn: policy}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0')
	)

	columns = [
		{'name': 'email', 'type': 'STRING', 'tags': {'governance.pii_category': 'email'}},
		{'name': 'age', 'type': 'INT'},
	]
	res = ResourceCreate(urn=urn, platform='databricks', name='table', attributes={'columns': columns})

	mock_state.needs_update.return_value = True
	mock_state.get_table_binding.return_value = None

	enforcer.enforce(bundle, [res])

	# Verify Generation
	enforcer.compiler.databricks_gen.generate_masking_udf.assert_called_once()

	# Verify Alter Column
	bind_calls = [c for c in mock_executor.execute.call_args_list if 'ALTER COLUMN email SET MASK' in str(c)]
	assert len(bind_calls) == 1


def test_reconcile_masking_idempotent(enforcer, mock_executor, mock_state):
	urn = 'urn:databricks:ws:cat.schema.table'
	reason = ConflictTrace(
		winning_obligation_id='pol-1',
		winning_source_id='src-1',
		description='Test Policy',
	)
	policy = ResolvedPolicy(
		resource_urn=urn,
		privacy=EffectivePrivacy(
			method=PrivacyMethod.ANONYMIZATION,
			reason=reason,
		),
	)
	bundle = PolicyBundle(
		policies={urn: policy}, schema_version='1.0', metadata=BuildMetadata(compiler_version='0.1.0')
	)

	columns = [{'name': 'email', 'type': 'STRING', 'tags': {'governance.pii_category': 'email'}}]
	res = ResourceCreate(urn=urn, platform='databricks', name='table', attributes={'columns': columns})

	# Determine expected func name
	# "mask_anonymization_STRING"
	func_name = 'gov_cat.gov_schema.mask_anonymization_STRING'

	mock_state.needs_update.return_value = False
	binding = TableBinding(full_table_name='...', column_masks={'email': func_name})
	mock_state.get_table_binding.return_value = binding

	enforcer.enforce(bundle, [res])

	# Only schema creation
	ops = [c for c in mock_executor.execute.call_args_list if 'CREATE SCHEMA' not in str(c)]
	assert len(ops) == 0


# ==============================================================================
# Helper Methods: Column Detection
# ==============================================================================


def test_find_rls_column_explicit_tag(enforcer):
	cols = [{'name': 'a', 'type': 'INT'}, {'name': 'b', 'type': 'STRING'}]
	tags = {'ambyte.row_filter_column': 'b'}

	found = enforcer._find_rls_column(cols, tags)
	assert found['name'] == 'b'


def test_find_rls_column_explicit_tag_missing_col(enforcer, caplog):
	cols = [{'name': 'a'}]
	tags = {'ambyte.row_filter_column': 'z'}  # z does not exist

	found = enforcer._find_rls_column(cols, tags)
	assert found is None
	assert 'but column not found' in caplog.text


def test_find_rls_column_col_tag(enforcer):
	cols = [{'name': 'a', 'tags': {'governance.rls_key': 'true'}}, {'name': 'b'}]
	found = enforcer._find_rls_column(cols, {})
	assert found['name'] == 'a'


def test_find_rls_column_heuristic(enforcer):
	cols = [{'name': 'tenant_id'}]
	found = enforcer._find_rls_column(cols, {})
	assert found['name'] == 'tenant_id'


def test_find_sensitive_columns_mixed(enforcer):
	cols = [
		{'name': 'c1', 'tags': {'governance.is_sensitive': 'true'}},  # Tag 1
		{'name': 'c2', 'tags': {'governance.pii_category': 'meh'}},  # Tag 2
		{'name': 'email_address'},  # Heuristic
		{'name': 'safe'},
	]

	found = enforcer._find_sensitive_columns(cols)
	found_names = {c['name'] for c in found}
	assert found_names == {'c1', 'c2', 'email_address'}


# ==============================================================================
# Helper Methods: UDF Application
# ==============================================================================


def test_apply_udf_fallback_no_hash(enforcer, mock_executor, mock_state):
	"""If generated SQL has no hash in comment, force update."""
	sql_no_hash = 'CREATE FUNCTION foo...'
	enforcer._apply_udf('foo', sql_no_hash, dry_run=False)

	mock_state.needs_update.assert_not_called()  # Skipped check, forced true
	mock_executor.execute.assert_called_with(sql_no_hash)


def test_extract_content_hash(enforcer):
	sql = "CREATE ... COMMENT 'ambyte:v1:deadbeef' ..."
	assert enforcer._extract_content_hash(sql) == 'ambyte:v1:deadbeef'

	sql_bad = "CREATE ... COMMENT 'whatever' ..."
	assert enforcer._extract_content_hash(sql_bad) is None

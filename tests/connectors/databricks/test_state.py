from unittest.mock import MagicMock, patch

import pytest
from ambyte_databricks.state import GovernanceFunction, GovernanceState
from databricks.sdk.core import DatabricksError
from databricks.sdk.service.catalog import (
	ColumnInfo,
	ColumnMask,
	FunctionInfo,
	RowFilterOptions,
	TableInfo,
)

# ==============================================================================
# GovernanceFunction Tests
# ==============================================================================


def test_governance_function_hash_extraction():
	# Valid hash
	gf = GovernanceFunction(
		full_name='cat.sch.fn', definition='CREATE FUNCTION...', comment='ambyte:v1:abc123ef | User comment here'
	)
	assert gf.content_hash == 'ambyte:v1:abc123ef'

	# No comment
	gf_none = GovernanceFunction('n', 'd', comment=None)
	assert gf_none.content_hash is None

	# Empty comment
	gf_empty = GovernanceFunction('n', 'd', comment='')
	assert gf_empty.content_hash is None

	# Comment without hash
	gf_plain = GovernanceFunction('n', 'd', comment='Just a description')
	assert gf_plain.content_hash is None

	# Hash in middle (should fail regex requires start anchor)
	gf_mid = GovernanceFunction('n', 'd', comment='User comment | ambyte:v1:abc123ef')
	assert gf_mid.content_hash is None


# ==============================================================================
# GovernanceState Tests
# ==============================================================================


@pytest.fixture
def mock_client():
	return MagicMock()


@pytest.fixture
def state(mock_client):
	with patch('ambyte_databricks.state.settings') as s:
		s.GOVERNANCE_CATALOG = 'main_cat'
		s.GOVERNANCE_SCHEMA = 'gov_schema'
		return GovernanceState(mock_client)


def test_refresh_success(state, mock_client):
	# Setup mock return for list
	fn1 = MagicMock(spec=FunctionInfo)
	fn1.full_name = 'main_cat.gov_schema.fn1'
	fn1.routine_definition = 'def1'
	fn1.comment = 'ambyte:v1:111'

	fn2 = MagicMock(spec=FunctionInfo)
	fn2.full_name = 'main_cat.gov_schema.fn2'
	# missing definition, should trigger detail fetch
	fn2.routine_definition = None
	fn2.comment = None

	mock_client.functions.list.return_value = [fn1, fn2]

	# Setup mock return for get (detail fetch for fn2)
	fn2_detail = MagicMock(spec=FunctionInfo)
	fn2_detail.routine_definition = 'def2_fetched'
	fn2_detail.comment = 'ambyte:v1:222'
	mock_client.functions.get.return_value = fn2_detail

	state.refresh()

	assert state._loaded is True
	assert len(state._functions) == 2

	# Check Fn1
	f1 = state.get_function('fn1')
	assert f1.definition == 'def1'
	assert f1.content_hash == 'ambyte:v1:111'

	# Check Fn2 (fetched details)
	f2 = state.get_function('fn2')
	assert f2.definition == 'def2_fetched'
	assert f2.content_hash == 'ambyte:v1:222'

	# Verify call to get details for fn2
	mock_client.functions.get.assert_called_with('main_cat.gov_schema.fn2')


def test_refresh_schema_not_found(state, mock_client):
	# Simulate Schema Missing Error
	mock_client.functions.list.side_effect = DatabricksError('SCHEMA_NOT_FOUND')

	state.refresh()

	# Should handle gracefully and result in empty state
	assert state._loaded is True
	assert state._functions == {}


def test_refresh_generic_error(state, mock_client):
	mock_client.functions.list.side_effect = DatabricksError('INTERNAL_ERROR')

	with pytest.raises(DatabricksError):
		state.refresh()


def test_refresh_detail_fetch_error(state, mock_client):
	"""Test when fetching details for a specific function fails."""
	fn1 = MagicMock(spec=FunctionInfo)
	fn1.full_name = 'fn1'
	fn1.routine_definition = None  # force detail fetch

	mock_client.functions.list.return_value = [fn1]
	mock_client.functions.get.side_effect = DatabricksError('Access Denied')

	state.refresh()

	# Should skip fn1 but finish loading
	assert state._loaded is True
	assert 'fn1' not in state._functions


def test_get_function_auto_load(state, mock_client):
	"""Test that get_function calls refresh if not loaded."""
	mock_client.functions.list.return_value = []

	assert state._loaded is False
	state.get_function('something')
	assert state._loaded is True
	mock_client.functions.list.assert_called_once()


def test_get_function_names(state):
	# Manually populate for test
	state._functions = {'main_cat.gov_schema.my_func': GovernanceFunction('main_cat.gov_schema.my_func', '', '')}
	state._loaded = True

	# 1. Exact match
	assert state.get_function('main_cat.gov_schema.my_func') is not None

	# 2. Short name match (constructs full name)
	assert state.get_function('my_func') is not None

	# 3. Non-existent
	assert state.get_function('other_func') is None


def test_needs_update(state):
	# Setup existing function
	f_current = GovernanceFunction('f1', 'def', comment='ambyte:v1:abcdef123')
	f_legacy = GovernanceFunction('f2', 'def', comment='just a comment')

	state._functions = {'f1': f_current, 'f2': f_legacy}
	state._loaded = True

	# Case 1: Function doesn't exist => True
	assert state.needs_update('unknown_func', 'ambyte:v1:new') is True

	# Case 2: Function exists, Hash matches => False
	assert state.needs_update('f1', 'ambyte:v1:abcdef123') is False

	# Case 3: Function exists, Hash mismatch => True
	assert state.needs_update('f1', 'ambyte:v1:NEW_HASH') is True

	# Case 4: Function exists, No existing hash => True
	assert state.needs_update('f2', 'ambyte:v1:whatever') is True


def test_get_table_binding_found(state, mock_client):
	# Setup TableInfo
	row_filter = RowFilterOptions(function_name='main_cat.gov.filter_fn')

	# Mock ColumnInfo with Mask
	c1 = MagicMock(spec=ColumnInfo)
	c1.name = 'email'
	c1.mask = MagicMock(spec=ColumnMask)
	c1.mask.function_name = 'main_cat.gov.mask_email'

	c2 = MagicMock(spec=ColumnInfo)
	c2.name = 'id'
	c2.mask = None

	table = MagicMock(spec=TableInfo)
	table.full_name = 'prod.sales.customers'
	table.row_filter = row_filter
	table.columns = [c1, c2]

	mock_client.tables.get.return_value = table

	# Execute
	binding = state.get_table_binding('prod.sales.customers')

	# Verify
	assert binding is not None
	assert binding.full_table_name == 'prod.sales.customers'
	assert binding.row_filter_func == 'main_cat.gov.filter_fn'

	# Check masks
	assert 'email' in binding.column_masks
	assert binding.column_masks['email'] == 'main_cat.gov.mask_email'
	assert 'id' not in binding.column_masks


def test_get_table_binding_not_found(state, mock_client):
	mock_client.tables.get.side_effect = DatabricksError('TABLE_NOT_FOUND')

	binding = state.get_table_binding('missing.table')
	assert binding is None


def test_refresh_skips_empty_fullname_in_list(state, mock_client):
	"""Ensure it gracefully skips entries with empty names if SDK returns odd data."""
	fn_bad = MagicMock(spec=FunctionInfo)
	fn_bad.full_name = None  # Weird case

	mock_client.functions.list.return_value = [fn_bad]
	state.refresh()
	assert len(state._functions) == 0


def test_get_table_binding_minimal(state, mock_client):
	"""Test table with no filters or columns."""
	table = MagicMock(spec=TableInfo)
	table.full_name = 'tab'
	table.row_filter = None
	table.columns = None  # SDK might return None if no columns fetched/exist?

	mock_client.tables.get.return_value = table

	binding = state.get_table_binding('tab')
	assert binding.row_filter_func is None
	assert binding.column_masks == {}

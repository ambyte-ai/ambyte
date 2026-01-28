from unittest.mock import patch

import pytest
from ambyte_databricks.config import settings
from ambyte_databricks.crawler import UnityCatalogCrawler
from databricks.sdk.core import DatabricksError
from databricks.sdk.service.catalog import (
	CatalogInfo,
	ColumnInfo,
	EntityTagAssignment,
	SchemaInfo,
	TableType,
)


@pytest.fixture
def crawler(mock_db_client):
	return UnityCatalogCrawler(client=mock_db_client)


class TestUnityCatalogCrawler:
	def test_init(self, crawler, mock_db_client):
		"""Test initialization of the crawler."""
		assert crawler.client == mock_db_client

	def test_matches_any_pattern(self, crawler):
		"""Test the glob pattern matching logic."""
		# Exact match
		assert crawler._matches_any_pattern('sales', ['sales']) is True
		# Wildcard
		assert crawler._matches_any_pattern('sales', ['*']) is True
		# Prefix
		assert crawler._matches_any_pattern('prod_db', ['prod_*']) is True
		# Suffix
		assert crawler._matches_any_pattern('data_v2', ['*_v2']) is True
		# No match
		assert crawler._matches_any_pattern('dev_db', ['prod_*']) is False
		# Empty patterns
		assert crawler._matches_any_pattern('anything', []) is False

	@patch.object(settings, 'EXCLUDE_CATALOGS', ['ignore_*'])
	@patch.object(settings, 'INCLUDE_CATALOGS', ['prod_*', 'main'])
	def test_should_scan_catalog(self, crawler):
		"""Test catalog filtering logic."""
		# Included
		assert crawler._should_scan_catalog('prod_db') is True
		assert crawler._should_scan_catalog('main') is True

		# Excluded (overrides include)
		assert crawler._should_scan_catalog('ignore_prod') is False

		# Not included
		assert crawler._should_scan_catalog('dev_db') is False

	@patch.object(settings, 'EXCLUDE_SCHEMAS', ['tmp_*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_should_scan_schema(self, crawler):
		"""Test schema filtering logic."""
		# Included
		assert crawler._should_scan_schema('sales') is True

		# Excluded
		assert crawler._should_scan_schema('tmp_data') is False

	def test_crawl_empty_catalogs(self, crawler, mock_db_client):
		"""Test crawl with no catalogs found."""
		mock_db_client.catalogs.list.return_value = []

		assets = list(crawler.crawl())

		assert len(assets) == 0
		mock_db_client.catalogs.list.assert_called_once()
		mock_db_client.schemas.list.assert_not_called()

	def test_crawl_catalog_list_error(self, crawler, mock_db_client):
		"""Test handling of error when listing catalogs."""
		mock_db_client.catalogs.list.side_effect = DatabricksError('API Error')

		assets = list(crawler.crawl())

		assert len(assets) == 0
		mock_db_client.catalogs.list.assert_called_once()

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_skip_filtered_catalog(self, crawler, mock_db_client, make_catalog):
		"""Test that filtered-out catalogs are skipped."""
		# Setup: catalog "ignore_me" should be filtered out if we set exclusions
		with patch.object(settings, 'EXCLUDE_CATALOGS', ['ignore_*']):
			cats = [make_catalog('ignore_me'), make_catalog('good_cat')]
			mock_db_client.catalogs.list.return_value = cats
			mock_db_client.schemas.list.return_value = []

			list(crawler.crawl())

			# verify we only listed schemas for good_cat
			mock_db_client.schemas.list.assert_called_once_with('good_cat')

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_schema_list_error(self, crawler, mock_db_client, make_catalog):
		"""Test handling of error when listing schemas."""
		mock_db_client.catalogs.list.return_value = [make_catalog('main')]
		mock_db_client.schemas.list.side_effect = DatabricksError('Schema Access Denied')

		assets = list(crawler.crawl())

		assert len(assets) == 0
		mock_db_client.schemas.list.assert_called_once_with('main')
		# Should continue without crashing (handled in loop)

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_skip_filtered_schema(self, crawler, mock_db_client, make_catalog, make_schema):
		"""Test that filtered-out schemas are skipped."""
		with patch.object(settings, 'EXCLUDE_SCHEMAS', ['ignore_*']):
			mock_db_client.catalogs.list.return_value = [make_catalog('main')]
			schemas = [make_schema('ignore_schema', 'main'), make_schema('good_schema', 'main')]
			mock_db_client.schemas.list.return_value = schemas
			mock_db_client.tables.list.return_value = []

			list(crawler.crawl())

			mock_db_client.tables.list.assert_called_once_with('main', 'good_schema')

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_table_list_error(self, crawler, mock_db_client, make_catalog, make_schema):
		"""Test handling of error when listing tables."""
		mock_db_client.catalogs.list.return_value = [make_catalog('main')]
		mock_db_client.schemas.list.return_value = [make_schema('default', 'main')]
		mock_db_client.tables.list.side_effect = DatabricksError('Table Access Denied')

		assets = list(crawler.crawl())

		assert len(assets) == 0
		mock_db_client.tables.list.assert_called_once_with('main', 'default')

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_success_with_tags(self, crawler, mock_db_client, make_catalog, make_schema, make_table):
		"""Test successful crawl including fetching tags for valid table types."""
		# Setup Hierarchy
		catalog = make_catalog('main')
		schema = make_schema('default', 'main')

		# Table 1: Managed table with tags
		t1_cols = [{'name': 'col1', 'type': 'STRING'}]
		table1 = make_table('table1', 'default', 'main', columns=t1_cols, table_type=TableType.MANAGED)

		# Table 2: View with no tags
		table2 = make_table('view1', 'default', 'main', table_type=TableType.VIEW)

		# Table 3: External table (to ensure coverage of list)
		table3 = make_table('ext1', 'default', 'main', table_type=TableType.EXTERNAL)

		# Mocks
		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table1, table2, table3]

		# Tags setup
		# table1 tags: table level + col1
		# table2: empty tags (simulated)
		# table3: empty tags

		def assign_tags_side_effect(entity_type, entity_name):
			if entity_name == table1.full_name and entity_type == 'tables':
				return [
					EntityTagAssignment(
						entity_name=table1.full_name, entity_type='tables', tag_key='pii', tag_value='true'
					)
				]
			if entity_name == f'{table1.full_name}.col1' and entity_type == 'columns':
				return [
					EntityTagAssignment(
						entity_name=f'{table1.full_name}.col1',
						entity_type='columns',
						tag_key='sensitive',
						tag_value='high',
					)
				]
			return []

		mock_db_client.entity_tag_assignments.list.side_effect = assign_tags_side_effect

		assets = list(crawler.crawl())

		assert len(assets) == 3

		# Check Asset 1 (Table 1)
		asset1 = assets[0]
		assert asset1.table_info.name == 'table1'
		assert asset1.tags == {'pii': 'true'}
		assert asset1.column_tags == {'col1': {'sensitive': 'high'}}

		# Check Asset 2 (View 1)
		asset2 = assets[1]
		assert asset2.table_info.name == 'view1'
		assert asset2.tags == {}

		# Check Asset 3 (Ext 1)
		asset3 = assets[2]
		assert asset3.table_info.name == 'ext1'

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_crawl_skips_tags_for_unsupported_type(
		self, crawler, mock_db_client, make_catalog, make_schema, make_table
	):
		"""Test that we don't try to fetch tags for unsupported table types (e.g. MATERIALIZED_VIEW if excluded from list)."""
		# Note: Code explicitly checks [MANAGED, EXTERNAL, VIEW]
		# Let's create a dummy type if possible or just rely on logic
		# Since TableType is an Enum in definitions, we can use a mock or a different enum value if available
		# But SDK might restrict it. Let's use a mocked object with a different type string if enum allows,
		# or just assume MATERIALIZED_VIEW is not in the list.

		catalog = make_catalog('main')
		schema = make_schema('default', 'main')
		# Assume 'FOREIGN' or something else not in the allowed list
		# We need to force table_type to be something else.
		table_weird = make_table('weird', 'default', 'main')
		# Force overwrite type
		table_weird.table_type = 'UNKNOWN_TYPE'

		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table_weird]

		assets = list(crawler.crawl())

		assert len(assets) == 1
		assert assets[0].tags == {}
		# Ensure tag client was NOT called
		mock_db_client.entity_tag_assignments.list.assert_not_called()

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_tags_fetch_error_handling(self, crawler, mock_db_client, make_catalog, make_schema, make_table):
		"""Test robustness when tag fetching fails."""
		catalog = make_catalog('main')
		schema = make_schema('default', 'main')
		t_cols = [{'name': 'col1', 'type': 'STRING'}, {'name': 'col2', 'type': 'INT'}]
		table = make_table('tbl', 'default', 'main', columns=t_cols)

		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table]

		# Error on table tags: Should normally be swallowed
		# Error on column tags: Should be swallowed

		# To test specific branches:
		# 1. table tags fail -> empty entity tags
		# 2. column tags fail for one column -> empty tags for that column

		def assign_tags_side_effect(entity_type, entity_name):
			if entity_type == 'tables':
				raise DatabricksError('Tag API down')
			if entity_type == 'columns':
				# Fail for col1, work for col2
				if 'col1' in entity_name:
					raise DatabricksError('Col API down')
				if 'col2' in entity_name:
					return [
						EntityTagAssignment(
							entity_name=entity_name, entity_type=entity_type, tag_key='ok', tag_value='yes'
						)
					]
			return []

		mock_db_client.entity_tag_assignments.list.side_effect = assign_tags_side_effect

		assets = list(crawler.crawl())
		asset = assets[0]

		# If fetching table tags raises error, it hits the outer except block
		# and skips the entire column tag fetching block!
		# So if table tag fetch fails, column tags are NOT fetched.
		assert asset.tags == {}
		assert asset.column_tags == {}

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_column_tags_fetch_partial_error(self, crawler, mock_db_client, make_catalog, make_schema, make_table):
		"""Test robustness when ONE column tag fetch fails but others succeed."""
		catalog = make_catalog('main')
		schema = make_schema('default', 'main')
		t_cols = [{'name': 'col1', 'type': 'STRING'}, {'name': 'col2', 'type': 'INT'}]
		table = make_table('tbl', 'default', 'main', columns=t_cols)

		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table]

		def assign_tags_side_effect(entity_type, entity_name):
			if entity_type == 'tables':
				return []
			if entity_type == 'columns':
				if 'col1' in entity_name:
					raise DatabricksError('Col1 failed')
				if 'col2' in entity_name:
					return [
						EntityTagAssignment(
							entity_name=entity_name, entity_type=entity_type, tag_key='valid', tag_value='1'
						)
					]
			return []

		mock_db_client.entity_tag_assignments.list.side_effect = assign_tags_side_effect

		assets = list(crawler.crawl())
		asset = assets[0]

		# Col1 failed -> no entry
		# Col2 succeeded -> entry
		assert 'col1' not in asset.column_tags
		assert asset.column_tags['col2'] == {'valid': '1'}

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_tags_with_none_values(self, crawler, mock_db_client, make_catalog, make_schema, make_table):
		"""Test tag filtering when keys/values are None."""
		catalog = make_catalog('main')
		schema = make_schema('default', 'main')
		table = make_table('tbl', 'default', 'main', columns=[], table_type=TableType.MANAGED)

		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table]

		# Return tags with missing keys/values
		mock_db_client.entity_tag_assignments.list.return_value = [
			EntityTagAssignment(
				entity_name=table.full_name, entity_type='tables', tag_key=None, tag_value='val'
			),  # Should skip
			EntityTagAssignment(
				entity_name=table.full_name, entity_type='tables', tag_key='key', tag_value=None
			),  # Should skip? Code: if t.tag_key and t.tag_value is not None
			EntityTagAssignment(entity_name=table.full_name, entity_type='tables', tag_key='good', tag_value='val'),
		]

		assets = list(crawler.crawl())
		asset = assets[0]

		assert asset.tags == {'good': 'val'}

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_skip_columns_without_name(self, crawler, mock_db_client, make_catalog, make_schema, make_table):
		"""Test that columns with empty/None names are skipped."""
		catalog = make_catalog('main')
		schema = make_schema('default', 'main')
		# Column with no name
		col_no_name = ColumnInfo(name=None, type_text='STRING', position=0)
		col_good = ColumnInfo(name='good', type_text='STRING', position=1)

		table = make_table('tbl', 'default', 'main')
		table.columns = [col_no_name, col_good]

		mock_db_client.catalogs.list.return_value = [catalog]
		mock_db_client.schemas.list.return_value = [schema]
		mock_db_client.tables.list.return_value = [table]

		# Setup mock to track calls
		mock_tag_list = mock_db_client.entity_tag_assignments.list
		mock_tag_list.return_value = []

		list(crawler.crawl())

		# Should have called for 'good', but NOT for None
		# Retrieve all calls to entity_tag_assignments.list
		# Filter for column calls
		column_calls = [
			c.kwargs['entity_name'] for c in mock_tag_list.call_args_list if c.kwargs.get('entity_type') == 'columns'
		]

		assert any('good' in name for name in column_calls)
		assert not any('None' in name for name in column_calls)  # naive check

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_catalog_with_none_name(self, crawler, mock_db_client):
		"""Test skipping a catalog with None name."""
		cat = CatalogInfo(name=None)
		mock_db_client.catalogs.list.return_value = [cat]

		list(crawler.crawl())

		mock_db_client.schemas.list.assert_not_called()

	@patch.object(settings, 'INCLUDE_CATALOGS', ['*'])
	@patch.object(settings, 'INCLUDE_SCHEMAS', ['*'])
	def test_schema_with_none_name(self, crawler, mock_db_client, make_catalog):
		"""Test skipping schema with None name."""
		mock_db_client.catalogs.list.return_value = [make_catalog('main')]
		schema = SchemaInfo(name=None, catalog_name='main')
		mock_db_client.schemas.list.return_value = [schema]

		list(crawler.crawl())

		mock_db_client.tables.list.assert_not_called()

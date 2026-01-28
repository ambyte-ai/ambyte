from unittest.mock import patch

import pytest
from ambyte_databricks.crawler import DiscoveredAsset
from ambyte_databricks.mapper import ResourceMapper
from ambyte_schemas.models.inventory import ResourceCreate
from databricks.sdk.service.catalog import TableType

# Use the make_table fixture from conftest.py if available,
# otherwise we rely on the mocked behavior or direct instantiation if needed.


@pytest.mark.parametrize(
	'host_url,expected_id',
	[
		('https://adb-12345.1.azuredatabricks.net/', 'adb-12345'),
		('https://my-workspace.cloud.databricks.com', 'my-workspace'),
		('https://abc.def.ghi.jkl', 'abc'),
		('http://localhost:8080', 'localhost'),
		('simple-string', 'simple-string'),
	],
)
def test_extract_workspace_id(host_url, expected_id):
	"""
	Test the workspace ID extraction logic with various URL formats.
	"""
	# We strip the environment dependency by patching settings during init
	with patch('ambyte_databricks.mapper.settings') as mock_settings:
		mock_settings.HOST = host_url
		mapper = ResourceMapper()
		assert mapper._workspace_id == expected_id


def test_extract_workspace_id_exception_fallback():
	"""
	Test that the mapper falls back to a default value if URL parsing blows up.
	"""
	with patch('ambyte_databricks.mapper.settings') as mock_settings:
		mock_settings.HOST = 'https://valid.com'

		# Mock urlparse to raise an exception to trigger the except block in _extract_workspace_id
		with patch('ambyte_databricks.mapper.urlparse', side_effect=Exception('Parsing failed')):
			mapper = ResourceMapper()
			assert mapper._workspace_id == 'unknown-workspace'


def test_map_full_asset(make_table):
	"""
	Test mapping a fully populated asset with columns, tags, and column tags.
	"""
	# 1. Setup Data
	columns_data = [
		{'name': 'user_id', 'type': 'BIGINT'},
		{'name': 'email', 'type': 'STRING'},
		{'name': 'raw_data', 'type': 'BINARY'},
	]
	# make_table fixture helps create a TableInfo object
	table = make_table(
		name='users', schema='marketing', catalog='prod', columns=columns_data, table_type=TableType.MANAGED
	)

	# Add comments which might not be set by make_table
	table.columns[0].comment = 'Primary Key'
	table.columns[1].comment = 'User Email'
	table.columns[2].comment = None

	# Construct the intermediate asset
	asset = DiscoveredAsset(
		table_info=table,
		tags={'compliance': 'gdpr', 'tier': 'gold'},
		column_tags={'email': {'pii': 'true', 'category': 'contact'}, 'raw_data': {'do_not_scan': 'true'}},
	)

	# 2. Initialize Mapper
	with patch('ambyte_databricks.mapper.settings') as mock_settings:
		mock_settings.HOST = 'https://unit-test-ws.cloud.databricks.com'
		mapper = ResourceMapper()

	# 3. Execute
	resource = mapper.map(asset)

	# 4. Verify
	assert isinstance(resource, ResourceCreate)

	# URN Generation
	# Expected: urn:databricks:<workspace>:<catalog>.<schema>.<table> (all lower)
	expected_urn = 'urn:databricks:unit-test-ws:prod.marketing.users'.lower()
	assert resource.urn == expected_urn
	assert resource.name == 'users'
	assert resource.platform == 'databricks'

	# Attributes verification
	attrs = resource.attributes
	assert attrs['owner'] == 'test_owner'
	assert attrs['table_type'] == 'MANAGED'
	assert attrs['storage_location'] == 's3://bucket/users'
	# Timestamps come from the mock/fixture
	assert attrs['created_at'] == 123456789
	assert attrs['updated_at'] == 123456789
	assert attrs['tags'] == {'compliance': 'gdpr', 'tier': 'gold'}
	assert attrs['hierarchy'] == {'catalog': 'prod', 'schema': 'marketing'}

	# Columns verification
	assert len(attrs['columns']) == 3

	# Col 1: user_id
	c1 = attrs['columns'][0]
	assert c1['name'] == 'user_id'
	assert c1['type'] == 'BIGINT'
	assert c1['comment'] == 'Primary Key'
	# No tags for this one
	assert 'tags' not in c1

	# Col 2: email
	c2 = attrs['columns'][1]
	assert c2['name'] == 'email'
	assert c2['type'] == 'STRING'
	assert c2['comment'] == 'User Email'
	assert c2['tags'] == {'pii': 'true', 'category': 'contact'}

	# Col 3: raw_data
	c3 = attrs['columns'][2]
	assert c3['name'] == 'raw_data'
	assert c3['type'] == 'BINARY'
	assert c3['comment'] is None
	assert c3['tags'] == {'do_not_scan': 'true'}


def test_map_minimal_asset(make_table):
	"""
	Test mapping an asset with minimal information (no columns, no tags, no table type).
	"""
	# 1. Setup Data
	table = make_table(
		name='temp_data',
		schema='default',
		catalog='hive_metastore',
		columns=None,  # No columns
	)
	# Simulate missing table type (e.g. unknown in older versions or edge cases)
	table.table_type = None

	asset = DiscoveredAsset(table_info=table, tags={}, column_tags={})

	# 2. Initialize Mapper
	with patch('ambyte_databricks.mapper.settings') as mock_settings:
		mock_settings.HOST = 'https://legacy.databricks.com'
		mapper = ResourceMapper()

	# 3. Execute
	resource = mapper.map(asset)

	# 4. Verify
	# URN
	expected_urn = 'urn:databricks:legacy:hive_metastore.default.temp_data'.lower()
	assert resource.urn == expected_urn

	attrs = resource.attributes
	# Fallback for table_type
	assert attrs['table_type'] == 'UNKNOWN'
	assert attrs['tags'] == {}
	assert attrs['columns'] == []

	# Hierarchy
	assert attrs['hierarchy'] == {'catalog': 'hive_metastore', 'schema': 'default'}

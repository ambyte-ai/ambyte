import pytest
import yaml
from ambyte_cli.services.inventory import InventoryLoader
from pydantic import ValidationError

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_root(tmp_path):
	"""A clean workspace root."""
	return tmp_path


@pytest.fixture
def loader(mock_root):
	"""InventoryLoader instance pointed at mock_root."""
	return InventoryLoader(mock_root)


# ==============================================================================
# TESTS
# ==============================================================================


def test_load_missing_file_defaults(loader):
	"""
	If resources.yaml does not exist, the loader should return a
	default 'wildcard' resource to allow local development to proceed easily.
	"""
	resources = loader.load()

	assert len(resources) == 1
	assert resources[0].urn == 'urn:local:default'
	assert resources[0].description == 'Auto-generated default context'


def test_load_valid_inventory(loader, mock_root):
	"""
	Test loading a correctly formatted resources.yaml.
	"""
	content = {
		'resources': [
			{
				'urn': 'urn:snowflake:sales',
				'tags': {'env': 'prod', 'sensitivity': 'high'},
				'config': {'snowflake': {'database': 'SALES_DB'}},
			},
			{'urn': 'urn:s3:logs', 'tags': {'env': 'dev'}},
		]
	}

	file_path = mock_root / 'resources.yaml'
	with open(file_path, 'w') as f:
		yaml.dump(content, f)

	resources = loader.load()

	assert len(resources) == 2

	# Check Item 1
	r1 = resources[0]
	assert r1.urn == 'urn:snowflake:sales'
	assert r1.tags['env'] == 'prod'
	assert r1.config['snowflake']['database'] == 'SALES_DB'

	# Check Item 2
	r2 = resources[1]
	assert r2.urn == 'urn:s3:logs'
	assert r2.tags['env'] == 'dev'


def test_load_empty_file(loader, mock_root):
	"""
	If file exists but is empty/null, return empty list (no resources).
	"""
	file_path = mock_root / 'resources.yaml'
	file_path.touch()  # Create empty file

	resources = loader.load()
	assert resources == []


def test_invalid_yaml_syntax(loader, mock_root):
	"""
	Malformed YAML should raise YAMLError.
	"""
	file_path = mock_root / 'resources.yaml'
	file_path.write_text('resources: [unclosed list', encoding='utf-8')

	with pytest.raises(yaml.YAMLError):
		loader.load()


def test_schema_validation_missing_urn(loader, mock_root):
	"""
	Missing required fields (URN) should raise ValidationError.
	"""
	content = {
		'resources': [
			{
				# Missing URN
				'tags': {'env': 'prod'}
			}
		]
	}

	file_path = mock_root / 'resources.yaml'
	with open(file_path, 'w') as f:
		yaml.dump(content, f)

	with pytest.raises(ValidationError) as exc:
		loader.load()

	assert 'urn' in str(exc.value)


def test_schema_validation_bad_structure(loader, mock_root):
	"""
	Root key mismatch (e.g. 'inventory' instead of 'resources').
	"""
	content = {'wrong_key': [{'urn': 'urn:test'}]}

	file_path = mock_root / 'resources.yaml'
	with open(file_path, 'w') as f:
		yaml.dump(content, f)

	resources = loader.load()
	assert resources == []

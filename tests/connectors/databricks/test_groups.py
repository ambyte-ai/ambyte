import logging
from pathlib import Path

import pytest
from ambyte_databricks.groups import DEFAULT_MAPPING_PATH, GroupMapper


@pytest.fixture
def mock_mapping_file(tmp_path):
	"""Creates a temporary valid mapping file."""
	content = """
mappings:
  - purpose: "MARKETING"
    associated_groups:
      - "mkt-team"
      - "growth"
  - purpose: "ENGINEERING"
    associated_groups:
      - "devs"

default_admin_groups:
  - "super-admin"
"""
	p = tmp_path / 'groups.yaml'
	p.write_text(content, encoding='utf-8')
	return p


def test_init_defaults():
	mapper = GroupMapper()
	assert mapper.mapping_file == DEFAULT_MAPPING_PATH
	assert mapper._loaded is False


def test_load_valid_file(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	mapper.load()

	assert mapper._loaded is True
	# Verify cache content
	assert 'MARKETING' in mapper._cache
	assert 'ENGINEERING' in mapper._cache
	assert 'mkt-team' in mapper._cache['MARKETING']
	assert 'super-admin' in mapper._defaults


def test_load_idempotency(mock_mapping_file):
	"""Test that calling load() multiple times is safe and returns early."""
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	mapper.load()
	assert mapper._loaded is True

	# Call again to hit the early return (line 29)
	mapper.load()
	assert mapper._loaded is True


def test_resolve_groups_normal(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)

	# "MARKETING" -> mkt-team, growth
	# "ENGINEERING" -> devs
	# + default admin -> super-admin
	groups = mapper.resolve_groups(['MARKETING', 'ENGINEERING'])

	expected = {'mkt-team', 'growth', 'devs', 'super-admin'}
	assert set(groups) == expected


def test_resolve_groups_case_insensitive(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	groups = mapper.resolve_groups(['marketing', '  EngineerinG '])
	expected = {'mkt-team', 'growth', 'devs', 'super-admin'}
	assert set(groups) == expected


def test_resolve_groups_unknown_purpose(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	groups = mapper.resolve_groups(['UNKNOWN_PURPOSE'])

	# Should only return admin defaults
	assert set(groups) == {'super-admin'}


def test_resolve_groups_empty_input(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	groups = mapper.resolve_groups([])
	assert set(groups) == {'super-admin'}


def test_missing_file_handling(caplog):
	"""Test that a missing file logs a warning and results in empty mappings."""
	# Point to a non-existent file
	missing_path = Path('non_existent_file.yaml')
	mapper = GroupMapper(mapping_file=missing_path)

	with caplog.at_level(logging.WARNING):
		mapper.load()

	assert 'Group mapping file not found' in caplog.text
	# Should be "loaded" but empty
	assert (
		mapper._loaded is False
	)  # Wait, looking at code: `if not self.mapping_file.exists(): ... return` -> so _loaded remains False?
	# Actually, if it returns early, _loaded stays False.
	# Let's check the code behavior:
	# 31: if not self.mapping_file.exists(): ... return
	# So _loaded is NOT set to True.
	# But calling resolve_groups calls load() again.

	# Let's verify resolve_groups behavior with missing file
	groups = mapper.resolve_groups(['MARKETING'])
	assert groups == []  # No defaults, no mappings


def test_malformed_yaml_handling(tmp_path, caplog):
	"""Test that malformed YAML logs an error but doesn't crash."""
	bad_file = tmp_path / 'bad.yaml'
	bad_file.write_text('mappings:\n  - purpose: [broken', encoding='utf-8')

	mapper = GroupMapper(mapping_file=bad_file)

	with caplog.at_level(logging.ERROR):
		mapper.load()

	assert 'Failed to parse group mappings' in caplog.text
	# Code catches Exception and continues.
	# _loaded stays False because it is set at the end of the try block.
	assert mapper._loaded is False

	# Verify we can still call resolve_groups (safely returns empty/defaults if it had any before error, but here it failed)
	assert mapper.resolve_groups(['MARKETING']) == []


def test_admin_groups_property(mock_mapping_file):
	mapper = GroupMapper(mapping_file=mock_mapping_file)
	# Should auto-load
	admins = mapper.admin_groups
	assert admins == ['super-admin']
	assert mapper._loaded is True


def test_integration_default_path():
	"""
	Test using the actual default path if it exists locally.
	This is useful to verify the project structure isn't broken.
	"""
	if DEFAULT_MAPPING_PATH.exists():
		mapper = GroupMapper()
		mapper.load()
		assert mapper._loaded is True
		# Check basic sanity of the real file
		assert len(mapper._cache) > 0
		assert 'MARKETING' in mapper._cache
	else:
		pytest.skip('Default mapping file not found in environment')

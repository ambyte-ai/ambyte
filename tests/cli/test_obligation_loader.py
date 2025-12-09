from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from ambyte_cli.config import AmbyteConfig
from ambyte_cli.services.loader import ObligationLoader, PolicyLoaderError
from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	PrivacyMethod,
	RetentionTrigger,
)

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_policy_dir(tmp_path):
	"""Creates a temporary directory to act as the policies folder."""
	policies = tmp_path / 'policies'
	policies.mkdir()
	return policies


@pytest.fixture
def loader(mock_policy_dir):
	"""Returns an ObligationLoader configured to look in the temp dir."""
	config = AmbyteConfig(project_name='test', policies_dir=Path('policies'))

	loader_instance = ObligationLoader(config)
	# Manually override the resolved path to point to our temp fixture
	loader_instance.policy_dir = mock_policy_dir
	return loader_instance


# ==============================================================================
# TESTS: Parsing Logic (Unit)
# ==============================================================================


def test_parse_retention_policy(loader):
	"""Verify parsing of a RETENTION constraint."""
	raw_data = {
		'id': 'ret-1',
		'title': 'Keep 30 Days',
		'description': 'Test',
		'enforcement_level': 'BLOCKING',
		'provenance': {'source_id': 'GDPR', 'document_type': 'REG'},
		'constraint': {'type': 'RETENTION', 'duration': '30d', 'trigger': 'CREATION_DATE'},
	}

	ob = loader.parse_obligation_data(raw_data)

	assert ob.id == 'ret-1'
	assert ob.enforcement_level == EnforcementLevel.BLOCKING

	# Check Constraint Mapping
	assert ob.retention is not None
	assert ob.geofencing is None
	assert ob.retention.duration == timedelta(days=30)
	assert ob.retention.trigger == RetentionTrigger.CREATION_DATE


def test_parse_geofencing_policy(loader):
	"""Verify parsing of a GEOFENCING constraint."""
	raw_data = {
		'id': 'geo-1',
		'title': 'EU Only',
		'provenance': {'source_id': 'GDPR', 'document_type': 'REG'},
		'constraint': {'type': 'GEOFENCING', 'allowed_regions': ['DE', 'FR'], 'strict_residency': True},
	}

	ob = loader.parse_obligation_data(raw_data)

	assert ob.geofencing is not None
	assert ob.geofencing.allowed_regions == ['DE', 'FR']
	assert ob.geofencing.strict_residency is True


def test_parse_privacy_policy(loader):
	"""Verify parsing of PRIVACY_ENHANCEMENT with parameters."""
	raw_data = {
		'id': 'priv-1',
		'title': 'Differential Privacy',
		'provenance': {'source_id': 'GDPR', 'document_type': 'REG'},
		'constraint': {
			'type': 'PRIVACY_ENHANCEMENT',
			'method': 'DIFFERENTIAL_PRIVACY',
			'parameters': {'epsilon': '0.5'},
		},
	}

	ob = loader.parse_obligation_data(raw_data)

	assert ob.privacy is not None
	assert ob.privacy.method == PrivacyMethod.DIFFERENTIAL_PRIVACY
	assert ob.privacy.parameters['epsilon'] == '0.5'


def test_enum_resolution_case_insensitive(loader):
	"""
	Test that 'blocking', 'BLOCKING', and 'ENFORCEMENT_LEVEL_BLOCKING'
	all map to the correct enum.
	"""
	# 1. Lowercase short
	raw_1 = {
		'id': '1',
		'title': 'T',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'enforcement_level': 'blocking',
		'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'CREATION_DATE'},
	}
	ob1 = loader.parse_obligation_data(raw_1)
	assert ob1.enforcement_level == EnforcementLevel.BLOCKING

	# 2. Uppercase full
	raw_2 = {
		'id': '2',
		'title': 'T',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'enforcement_level': 'ENFORCEMENT_LEVEL_AUDIT_ONLY',
		'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'CREATION_DATE'},
	}
	ob2 = loader.parse_obligation_data(raw_2)
	assert ob2.enforcement_level == EnforcementLevel.AUDIT_ONLY


def test_duration_parsing(loader):
	"""Test helper method for duration parsing."""
	assert loader._parse_duration('30d') == timedelta(days=30)
	assert loader._parse_duration('24h') == timedelta(hours=24)
	assert loader._parse_duration('1y') == timedelta(days=365)

	with pytest.raises(ValueError):
		loader._parse_duration('invalid')


# ==============================================================================
# TESTS: Validation Errors
# ==============================================================================


def test_missing_required_fields(loader):
	"""Should raise error if ID or Title is missing."""
	raw_data = {
		# Missing ID and Title
		'description': 'incomplete',
		'provenance': {'source_id': 'X', 'document_type': 'Y'},
		'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'CREATION_DATE'},
	}

	with pytest.raises(PolicyLoaderError) as exc:
		loader.parse_obligation_data(raw_data)

	# Now it should hit the Pydantic ValidationError inside the loader
	assert 'Validation Failed' in str(exc.value)


def test_unknown_constraint_type(loader):
	"""Should raise error if constraint type is unknown."""
	raw_data = {
		'id': 'bad-1',
		'title': 'Bad',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'constraint': {'type': 'MAGIC_SPELL'},
	}

	with pytest.raises(PolicyLoaderError) as exc:
		loader.parse_obligation_data(raw_data)

	assert 'Unknown constraint type' in str(exc.value)


def test_invalid_enum_value(loader):
	"""Should raise error if enum value is nonsense."""
	raw_data = {
		'id': 'bad-2',
		'title': 'Bad',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'enforcement_level': 'MAYBE_SOMETIMES',
		'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'CREATION_DATE'},
	}

	with pytest.raises(PolicyLoaderError) as exc:
		loader.parse_obligation_data(raw_data)

	assert 'Invalid value' in str(exc.value)


# ==============================================================================
# TESTS: Directory Scanning (Integration)
# ==============================================================================


def test_load_all_success(loader, mock_policy_dir):
	"""Test loading multiple files from disk, including nested ones."""
	# File 1: Root
	f1 = mock_policy_dir / 'ob1.yaml'
	data1 = {
		'id': 'ob1',
		'title': 'T1',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'EVENT_DATE'},
	}
	with open(f1, 'w') as f:
		yaml.dump(data1, f)

	# File 2: Nested
	sub = mock_policy_dir / 'gdpr'
	sub.mkdir()
	f2 = sub / 'ob2.yml'  # Test .yml extension
	data2 = {
		'id': 'ob2',
		'title': 'T2',
		'provenance': {'source_id': 'S', 'document_type': 'D'},
		'constraint': {'type': 'GEOFENCING', 'allowed_regions': ['US']},
	}
	with open(f2, 'w') as f:
		yaml.dump(data2, f)

	# Run
	obligations = loader.load_all()

	assert len(obligations) == 2
	ids = sorted([o.id for o in obligations])
	assert ids == ['ob1', 'ob2']


def test_load_all_handles_corrupt_files(loader, mock_policy_dir, capsys):
	"""
	load_all() should not crash on a bad file, but print error to console
	and continue loading valid ones.
	"""
	# Valid file
	f1 = mock_policy_dir / 'good.yaml'
	with open(f1, 'w') as f:
		yaml.dump(
			{
				'id': 'good',
				'title': 'G',
				'provenance': {'source_id': 'S', 'document_type': 'D'},
				'constraint': {'type': 'RETENTION', 'duration': '1d', 'trigger': 'CREATION_DATE'},
			},
			f,
		)

	# Invalid YAML
	f2 = mock_policy_dir / 'bad.yaml'
	with open(f2, 'w') as f:
		f.write('id: [unclosed list')

	# Run
	obligations = loader.load_all()

	# Should have loaded the good one
	assert len(obligations) == 1
	assert obligations[0].id == 'good'

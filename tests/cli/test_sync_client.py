from pathlib import Path
from unittest import mock

import pytest
import yaml
from ambyte_cli.config import AmbyteConfig, CloudConfig
from ambyte_cli.services.sync import SyncService
from ambyte_schemas.models.obligation import EnforcementLevel, Obligation, SourceProvenance

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_config(tmp_path):
	"""Setup a mock config pointing to a temporary policies directory."""
	pol_dir = tmp_path / 'policies'
	pol_dir.mkdir()
	return AmbyteConfig(
		project_name='test-project', policies_dir=Path('policies'), cloud=CloudConfig(project_id='proj-123')
	)


@pytest.fixture
def mock_api_client():
	"""Mock the AmbyteClient (SDK)."""
	return mock.MagicMock()


@pytest.fixture
def sync_service(mock_config, mock_api_client, monkeypatch, tmp_path):
	"""Initialize SyncService with mocked root paths."""
	# Ensure the loader inside sync_service uses our tmp_path
	monkeypatch.setattr('ambyte_cli.config.get_workspace_root', lambda: tmp_path)
	return SyncService(mock_config, mock_api_client)


def make_ob(id_val: str, title: str = 'Title'):
	"""
	Helper to create valid Obligation schemas.
	We use Geofencing here because your Loader's duration parser ('30d')
	conflicts with Pydantic's JSON serialization ('P30D').
	"""
	return Obligation(
		id=id_val,
		title=title,
		description='Desc',
		provenance=SourceProvenance(source_id='SRC', document_type='REG'),
		enforcement_level=EnforcementLevel.BLOCKING,
		geofencing={'allowed_regions': ['US'], 'strict_residency': True},
	)


# ==============================================================================
# TESTS
# ==============================================================================


def test_fetch_remote_obligations_missing_project_id(sync_service):
	"""Verify ValueError if project is not linked."""
	sync_service.config.cloud.project_id = None
	with pytest.raises(ValueError, match='Project ID missing'):
		sync_service._fetch_remote_obligations()


def test_fetch_remote_obligations_api_error(sync_service, mock_api_client):
	"""Verify error propagation and logging."""
	mock_api_client.list_obligations.side_effect = Exception('API Down')
	with pytest.raises(Exception, match='API Down'):
		sync_service._fetch_remote_obligations()


def test_get_local_file_map_recursive(sync_service, mock_config, tmp_path):
	"""Verify crawler finds files and handles recursion safely."""
	base = tmp_path / 'policies'

	# 1. Valid root file
	f1 = base / 'root.yaml'
	f1.write_text(yaml.dump(make_ob('ob-1').model_dump(mode='json', exclude_none=True)))

	# 2. Valid nested file
	sub = base / 'nested'
	sub.mkdir()
	f2 = sub / 'child.yml'
	f2.write_text(yaml.dump(make_ob('ob-2').model_dump(mode='json', exclude_none=True)))

	# 3. Corrupt file (should be skipped by the loop)
	f3 = base / 'broken.yaml'
	f3.write_text('!!broken: [')

	file_map = sync_service._get_local_file_map()

	assert len(file_map) == 2
	assert 'ob-1' in file_map
	assert 'ob-2' in file_map


def test_pull_new_policy(sync_service, mock_api_client, mock_config):
	"""Scenario: Remote has a policy that does not exist locally."""
	remote_ob = make_ob('new-id')
	mock_api_client.list_obligations.return_value = [remote_ob.model_dump(mode='json')]

	result = sync_service.pull()

	assert len(result.actions) == 1
	assert result.actions[0].status == 'NEW'
	assert (mock_config.abs_policies_dir / 'new-id.yaml').exists()


def test_pull_unchanged_policy(sync_service, mock_api_client, mock_config):
	"""Scenario: Local and remote are identical (semantic check)."""
	ob = make_ob('same')
	local_path = mock_config.abs_policies_dir / 'same.yaml'

	# Add system timestamps to remote to verify they are ignored in comparison
	remote_data = ob.model_dump(mode='json')
	remote_data['created_at'] = '2025-01-01T00:00:00Z'

	sync_service._write_to_yaml(local_path, ob)
	mock_api_client.list_obligations.return_value = [remote_data]

	result = sync_service.pull()

	assert result.actions[0].status == 'UNCHANGED'


def test_pull_updated_policy(sync_service, mock_api_client, mock_config):
	"""Scenario: Remote title changed."""
	local_ob = make_ob('update-me', title='Old Title')
	remote_ob = make_ob('update-me', title='New Title')

	local_path = mock_config.abs_policies_dir / 'update-me.yaml'
	sync_service._write_to_yaml(local_path, local_ob)

	mock_api_client.list_obligations.return_value = [remote_ob.model_dump(mode='json')]

	result = sync_service.pull()

	assert result.actions[0].status == 'UPDATED'
	# Verify file content actually changed
	with open(local_path) as f:
		data = yaml.safe_load(f)
		assert data['title'] == 'New Title'


def test_pull_prune_deleted(sync_service, mock_api_client, mock_config):
	"""Scenario: Local file exists but is missing from remote, prune=True."""
	local_path = mock_config.abs_policies_dir / 'dead.yaml'
	sync_service._write_to_yaml(local_path, make_ob('dead'))

	mock_api_client.list_obligations.return_value = []  # Remote is empty

	# Test with prune disabled first
	result_no_prune = sync_service.pull(prune=False)
	assert len(result_no_prune.actions) == 0
	assert local_path.exists()

	# Test with prune enabled
	result_prune = sync_service.pull(prune=True)
	assert result_prune.actions[0].status == 'DELETED'
	assert not local_path.exists()


def test_pull_dry_run(sync_service, mock_api_client, mock_config):
	"""Verify no side effects in dry run mode."""
	mock_api_client.list_obligations.return_value = [make_ob('dry').model_dump(mode='json')]

	result = sync_service.pull(dry_run=True)

	assert result.actions[0].status == 'NEW'
	assert not (mock_config.abs_policies_dir / 'dry.yaml').exists()


def test_pull_force_flag(sync_service, mock_api_client, mock_config):
	"""Verify force flag overwrites even if semantically identical."""
	ob = make_ob('force-test')
	local_path = mock_config.abs_policies_dir / 'force-test.yaml'
	sync_service._write_to_yaml(local_path, ob)

	mock_api_client.list_obligations.return_value = [ob.model_dump(mode='json')]

	# Mock the write method to verify it's called
	with mock.patch.object(sync_service, '_write_to_yaml') as mock_write:
		sync_service.pull(force=True)
		mock_write.assert_called_once()


def test_yaml_formatting_block_style(sync_service, tmp_path):
	"""Verify that multiline descriptions use YAML block scalar style (|)."""
	out_path = tmp_path / 'format.yaml'
	ob = make_ob('fmt')
	ob.description = 'Line 1\nLine 2\nLine 3'

	sync_service._write_to_yaml(out_path, ob)

	content = out_path.read_text()
	assert 'description: |' in content
	assert 'Line 1' in content
	assert 'Line 2' in content


def test_check_if_changed_corrupt_local(sync_service, tmp_path):
	"""Corruption should return True (triggering an overwrite/fix)."""
	bad_path = tmp_path / 'corrupt.yaml'
	bad_path.write_text('invalid: [yaml')

	is_changed = sync_service._check_if_changed(bad_path, make_ob('any'))
	assert is_changed is True

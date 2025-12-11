import pytest
import subprocess
from unittest import mock
from pathlib import Path

from ambyte_cli.config import AmbyteConfig
from ambyte_cli.services.git import GitHistoryLoader

# ==============================================================================
# FIXTURES & MOCK HELPERS
# ==============================================================================


@pytest.fixture
def mock_config(tmp_path):
	"""
	Creates a dummy config. The actual path doesn't matter since we mock git,
	but we provide a valid path object to satisfy type checks.
	"""
	return AmbyteConfig(project_name='test', policies_dir=Path('policies'))


@pytest.fixture
def loader(mock_config):
	with mock.patch('ambyte_cli.config.get_workspace_root', return_value=mock_config.policies_dir):
		yield GitHistoryLoader(mock_config)


@pytest.fixture
def mock_git(loader):
	"""
	Patches the _run_git method to avoid actual subprocess calls.
	Returns the mock object so tests can configure side_effects.
	"""
	with mock.patch.object(loader, '_run_git') as mock_run:
		yield mock_run


# ==============================================================================
# TESTS
# ==============================================================================


def test_load_at_revision_success(loader, mock_git):
	"""
	Happy path:
	1. Verify revision exists.
	2. List files.
	3. Read file content.
	4. Parse successfully.
	"""

	# Define side effects for the sequence of git calls
	def side_effect(args):
		cmd = args[0]
		# 1. Verify revision
		if cmd == 'rev-parse':
			return 'commit_hash'

		# 2. List files (git ls-tree)
		if cmd == 'ls-tree':
			return 'policies/gdpr.yaml\npolicies/retention.yaml'

		# 3. Read content (git show)
		if cmd == 'show':
			# Check which file is being requested
			ref = args[1]
			if 'gdpr.yaml' in ref:
				return """
                id: gdpr-1
                title: GDPR
                provenance: {source_id: "EU", document_type: "REG"}
                constraint: {type: "GEOFENCING", allowed_regions: ["EU"]}
                """
			if 'retention.yaml' in ref:
				return """
                id: ret-1
                title: Retention
                provenance: {source_id: "Corp", document_type: "POL"}
                constraint: {type: "RETENTION", duration: "1y", trigger: "CREATION_DATE"}
                """
		return ''

	mock_git.side_effect = side_effect

	obligations = loader.load_at_revision('HEAD')

	assert len(obligations) == 2
	ids = sorted([o.id for o in obligations])
	assert ids == ['gdpr-1', 'ret-1']

	# Verify parsing correctness for one
	gdpr = next(o for o in obligations if o.id == 'gdpr-1')
	assert gdpr.geofencing.allowed_regions == ['EU']


def test_revision_not_found(loader, mock_git):
	"""
	If git rev-parse fails, it should raise ValueError.
	"""
	# Simulate git returning non-zero exit code
	mock_git.side_effect = subprocess.CalledProcessError(128, ['git', 'rev-parse'])

	with pytest.raises(ValueError) as exc:
		loader.load_at_revision('invalid-hash')

	assert 'not found' in str(exc.value)


def test_skip_non_yaml_files(loader, mock_git):
	"""
	Should filter out non-.yaml files from ls-tree output.
	"""

	def side_effect(args):
		if args[0] == 'rev-parse':
			return 'hash'
		if args[0] == 'ls-tree':
			return 'policies/readme.md\npolicies/script.py\npolicies/policy.yaml'
		if args[0] == 'show':
			# Should only be called for the yaml file
			if 'policy.yaml' in args[1]:
				return """
                id: p1
                title: P1
                provenance: {source_id: "S", document_type: "D"}
                constraint: {type: "RETENTION", duration: "1d", trigger: "EVENT_DATE"}
                """
			# Raise error if it tries to read the markdown file
			raise RuntimeError(f'Should not read {args[1]}')
		return ''

	mock_git.side_effect = side_effect

	obs = loader.load_at_revision('HEAD')

	assert len(obs) == 1
	assert obs[0].id == 'p1'


def test_handle_broken_historical_file(loader, mock_git):
	"""
	If a file in history contains invalid YAML (or invalid schema),
	it should be skipped/logged, but not crash the entire loading process.
	"""

	def side_effect(args):
		if args[0] == 'rev-parse':
			return 'hash'
		if args[0] == 'ls-tree':
			return 'policies/broken.yaml'
		if args[0] == 'show':
			return 'id: [unclosed list'  # Invalid YAML
		return ''

	mock_git.side_effect = side_effect

	# Should not raise
	obs = loader.load_at_revision('HEAD')

	# Should result in empty list (failed file skipped)
	assert len(obs) == 0


def test_get_changed_files(loader, mock_git):
	"""
	Test wrapping git diff.
	"""
	mock_git.return_value = 'policies/new.yaml\npolicies/updated.yaml'

	files = loader.get_changed_files('HEAD~1')

	assert len(files) == 2
	assert 'policies/new.yaml' in files

	# Verify call args
	call_args = mock_git.call_args[0][0]
	assert call_args[0] == 'diff'
	assert call_args[2] == 'HEAD~1'


def test_subprocess_execution(loader, mock_config):
	"""
	Test the actual _run_git method (unmocked) to verify subprocess arguments.
	We mock subprocess.run instead of loader._run_git.
	"""
	real_loader = GitHistoryLoader(mock_config)

	# Mock config path resolution for CWD
	with mock.patch('ambyte_cli.config.get_workspace_root', return_value=Path('/tmp/root')):
		with mock.patch('subprocess.run') as mock_run:
			mock_run.return_value.stdout = 'output'
			mock_run.return_value.returncode = 0

			output = real_loader._run_git(['status'])

			assert output == 'output'

			# Verify arguments passed to subprocess
			mock_run.assert_called_once()
			args, kwargs = mock_run.call_args

			cmd_list = args[0]
			assert cmd_list == ['git', 'status']

			assert kwargs['cwd'] == Path('/tmp/root')
			assert kwargs['check'] is True
			assert kwargs['capture_output'] is True

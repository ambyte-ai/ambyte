import os
import stat
import sys
from unittest import mock

import ambyte_cli.services.auth as auth_mod
import yaml
from ambyte_cli.services.auth import CredentialsManager

# ==============================================================================
# TESTS: Precedence & Environment
# ==============================================================================


def test_get_api_key_env_var_precedence(mock_credentials_file, monkeypatch):
	"""
	Verify that AMBYTE_API_KEY environment variable takes precedence over the file.
	"""
	# 1. Setup file with one key
	mock_credentials_file(api_key='sk_live_file_key')

	# 2. Setup env var with another key
	monkeypatch.setenv('AMBYTE_API_KEY', 'sk_live_env_key')

	mgr = CredentialsManager()
	assert mgr.get_api_key() == 'sk_live_env_key'


def test_get_api_key_from_file(mock_credentials_file, monkeypatch):
	"""
	Verify retrieval from file when no env var is set.
	"""
	mock_credentials_file(api_key='sk_live_from_file')
	monkeypatch.delenv('AMBYTE_API_KEY', raising=False)

	mgr = CredentialsManager()
	assert mgr.get_api_key() == 'sk_live_from_file'


def test_bootstrap_env_loading(tmp_path, monkeypatch):
	"""
	Verify that the manager attempts to load .env from CWD and Workspace Root.
	"""
	# 1. Setup dummy paths
	root = tmp_path / 'project'
	cwd = root / 'subdir'
	cwd.mkdir(parents=True)

	# 2. Make it a valid Ambyte workspace
	(root / '.ambyte').mkdir()

	# 3. CREATE the .env files so the .exists() check passes in the source code
	cwd_env = cwd / '.env'
	cwd_env.touch()

	root_env = root / '.env'
	root_env.touch()

	# 4. Change directory to the subdir
	monkeypatch.chdir(cwd)

	# 5. Mock load_dotenv and verify calls
	with mock.patch('ambyte_cli.services.auth.load_dotenv') as mock_load:
		mgr = CredentialsManager()
		mgr._bootstrap_env()

		# Should be called once for CWD and once for Root
		assert mock_load.call_count == 2

		# Verify it looked for the root .env specifically
		mock_load.assert_any_call(dotenv_path=str(root_env.absolute()))
		# Verify it looked for the CWD .env specifically
		mock_load.assert_any_call(dotenv_path=str(cwd_env.absolute()))


# ==============================================================================
# TESTS: Loading & Validation
# ==============================================================================


def test_load_nonexistent_file(no_credentials):
	"""Should return None if file is missing."""
	mgr = CredentialsManager()
	assert mgr.load() is None


def test_load_invalid_yaml(mock_credentials_path):
	"""Should return None and log warning if YAML is corrupt."""
	creds_file = mock_credentials_path / 'credentials'
	creds_file.write_text("default: { api_key: 'unclosed quote", encoding='utf-8')

	mgr = CredentialsManager()
	assert mgr.load() is None


def test_load_schema_mismatch(mock_credentials_path):
	"""Should return None if required fields are missing."""
	creds_file = mock_credentials_path / 'credentials'
	# Missing api_key
	creds_file.write_text("default: { project_id: '123' }", encoding='utf-8')

	mgr = CredentialsManager()
	assert mgr.load() is None


def test_load_specific_profile(mock_credentials_file):
	"""Verify loading a non-default profile."""
	mock_credentials_file(api_key='sk_prod', profile='prod')

	mgr = CredentialsManager(profile='prod')
	creds = mgr.load()
	assert creds.api_key == 'sk_prod'


# ==============================================================================
# TESTS: Saving & Persistence
# ==============================================================================


def test_save_new_credentials(no_credentials):
	"""Verify creating a credentials file from scratch."""
	mgr = CredentialsManager()
	mgr.save(api_key='sk_new', project_id='p1', org_id='o1')

	# Use the path provided by the fixture or auth_mod.CREDENTIALS_FILE
	assert auth_mod.CREDENTIALS_FILE.exists()

	with open(auth_mod.CREDENTIALS_FILE) as f:
		data = yaml.safe_load(f)

	assert data['default']['api_key'] == 'sk_new'
	assert data['default']['project_id'] == 'p1'

	# Skip permission check on Windows as chmod works differently
	if sys.platform != 'win32':
		mode = os.stat(auth_mod.CREDENTIALS_FILE).st_mode
		assert stat.S_IMODE(mode) == stat.S_IRUSR | stat.S_IWUSR


def test_save_merges_profiles(mock_credentials_file):
	"""Verify that saving one profile doesn't wipe others."""
	mock_credentials_file(api_key='sk_default', profile='default')

	# Save a second profile
	mgr_prod = CredentialsManager(profile='prod')
	mgr_prod.save(api_key='sk_prod')

	with open(auth_mod.CREDENTIALS_FILE) as f:
		data = yaml.safe_load(f)

	assert 'default' in data
	assert 'prod' in data
	assert data['default']['api_key'] == 'sk_default'
	assert data['prod']['api_key'] == 'sk_prod'


# ==============================================================================
# TESTS: Logout & Helper Properties
# ==============================================================================


def test_delete_profile(mock_credentials_file):
	"""Verify removing a single profile."""
	mock_credentials_file(api_key='sk1', profile='p1')
	# Manually add a second profile to the file
	with open(auth_mod.CREDENTIALS_FILE) as f:
		data = yaml.safe_load(f)
	data['p2'] = {'api_key': 'sk2'}
	with open(auth_mod.CREDENTIALS_FILE, 'w') as f:
		yaml.dump(data, f)

	mgr = CredentialsManager(profile='p1')
	mgr.delete()

	with open(auth_mod.CREDENTIALS_FILE) as f:
		remaining = yaml.safe_load(f)

	assert 'p1' not in remaining
	assert 'p2' in remaining


def test_delete_on_missing_file(no_credentials):
	"""Should not crash if deleting when no file exists."""
	mgr = CredentialsManager()
	mgr.delete()  # Should return silently


def test_is_authenticated_property(mock_credentials_file, monkeypatch):
	"""Verify the boolean helper."""
	monkeypatch.delenv('AMBYTE_API_KEY', raising=False)

	mgr = CredentialsManager()

	# False initially
	assert mgr.is_authenticated is False

	# True after file setup
	mock_credentials_file()
	assert mgr.is_authenticated is True

	# True if env var exists (even if no file)
	monkeypatch.setenv('AMBYTE_API_KEY', 'sk_test')
	assert mgr.is_authenticated is True

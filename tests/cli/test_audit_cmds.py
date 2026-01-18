from unittest import mock

import pytest
from ambyte_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES & MOCK DATA
# ==============================================================================


@pytest.fixture
def mock_client():
	"""
	Patches the CloudApiClient instantiation within the command module.
	Returns the mock instance so we can configure return values per test.
	"""
	with mock.patch('ambyte_cli.commands.audit.CloudApiClient') as mock_cls:
		# We also need to mock load_config so the client constructor doesn't fail
		with mock.patch('ambyte_cli.commands.audit.load_config'):
			client_instance = mock_cls.return_value
			yield client_instance


@pytest.fixture
def sample_proof():
	"""Returns a valid-looking proof dictionary structure."""
	return {
		'entry': {
			'id': 'log-123',
			'entry_hash': 'valid_hash_123',
			'decision': 'ALLOW',
			'actor': {'id': 'user_alice'},
			'action': 'read',
			'timestamp': '2025-01-01T12:00:00Z',
			# Add other fields required by compute_local_entry_hash if strict
			'resource_urn': 'urn:test',
			'evaluation_trace': None,
			'request_context': {},
		},
		'block_header': {
			'merkle_root': 'root_hash',
			'signature': 'sig_hex',
			'sequence_index': 5,
			'timestamp_end': '2025-01-01T13:00:00Z',
			'prev_block_hash': 'prev',
			'log_count': 10,
		},
		'merkle_siblings': ['sib1', 'sib2'],
	}


# ==============================================================================
# TESTS: Audit Verify
# ==============================================================================


def test_verify_missing_public_key():
	"""
	Should fail if --key is not provided and env var is not set.
	"""
	# Ensure env var is unset
	with mock.patch.dict('os.environ', {}, clear=True):
		result = runner.invoke(app, ['audit', 'verify', 'log-123'])

	assert result.exit_code == 1
	assert 'Missing Public Key' in result.stdout


def test_verify_success(mock_client, sample_proof):
	"""
	Happy Path: All checks pass (Content, Merkle, Signature).
	"""
	mock_client.get_audit_proof.return_value = sample_proof

	# We mock the Verifier logic to return True/Matching values
	with mock.patch('ambyte_cli.commands.audit.AuditVerifier') as mock_verifier:
		# 1. Content Integrity: Returns hash matching the server entry
		mock_verifier.compute_local_entry_hash.return_value = 'valid_hash_123'
		# 2. Inclusion Integrity
		mock_verifier.verify_merkle_path.return_value = True
		# 3. Authority Integrity
		mock_verifier.verify_block_signature.return_value = True

		result = runner.invoke(app, ['audit', 'verify', 'log-123', '--key', 'aabbcc'])

	assert result.exit_code == 0
	assert 'AUTHENTIC AUDIT LOG' in result.stdout
	assert 'Content Integrity Verified' in result.stdout
	assert 'Inclusion Verified' in result.stdout
	assert 'Block Signature Verified' in result.stdout


def test_verify_content_tampering(mock_client, sample_proof):
	"""
	Scenario: Local hash calculation differs from what the server stored.
	This implies the log details (e.g. decision, actor) were modified in the DB.
	"""
	mock_client.get_audit_proof.return_value = sample_proof

	with mock.patch('ambyte_cli.commands.audit.AuditVerifier') as mock_verifier:
		# Simulate mismatch
		mock_verifier.compute_local_entry_hash.return_value = 'DIFFERENT_HASH'

		result = runner.invoke(app, ['audit', 'verify', 'log-123', '--key', 'aabbcc'])

	assert result.exit_code == 1
	assert 'Content Tampering Detected' in result.stdout
	assert 'Server Hash: valid_hash_123' in result.stdout
	assert 'Local Hash:  DIFFERENT_HASH' in result.stdout


def test_verify_merkle_failure(mock_client, sample_proof):
	"""
	Scenario: Content is valid, but the Merkle Path doesn't resolve to the Block Root.
	Implies the log was not actually part of the claimed block (Fake Inclusion).
	"""
	mock_client.get_audit_proof.return_value = sample_proof

	with mock.patch('ambyte_cli.commands.audit.AuditVerifier') as mock_verifier:
		mock_verifier.compute_local_entry_hash.return_value = 'valid_hash_123'
		# Merkle Check Fails
		mock_verifier.verify_merkle_path.return_value = False

		result = runner.invoke(app, ['audit', 'verify', 'log-123', '--key', 'aabbcc'])

	assert result.exit_code == 1
	assert 'Merkle Proof Failed' in result.stdout


def test_verify_signature_failure(mock_client, sample_proof):
	"""
	Scenario: Content and Path are valid, but the Block Header signature is invalid.
	Implies the Block itself was forged or the Public Key is wrong.
	"""
	mock_client.get_audit_proof.return_value = sample_proof

	with mock.patch('ambyte_cli.commands.audit.AuditVerifier') as mock_verifier:
		mock_verifier.compute_local_entry_hash.return_value = 'valid_hash_123'
		mock_verifier.verify_merkle_path.return_value = True
		# Signature Check Fails
		mock_verifier.verify_block_signature.return_value = False

		result = runner.invoke(app, ['audit', 'verify', 'log-123', '--key', 'aabbcc'])

	assert result.exit_code == 1
	assert 'Invalid Block Signature' in result.stdout


def test_verify_api_error(mock_client):
	"""
	Scenario: The API client raises an exception (e.g. 404 Not Found).
	"""
	mock_client.get_audit_proof.side_effect = Exception('Log not found')

	result = runner.invoke(app, ['audit', 'verify', 'missing-log', '--key', 'abc'])

	assert result.exit_code == 1
	assert 'Verification Error' in result.stdout
	assert 'Log not found' in result.stdout


def test_verify_verbose_flag(mock_client, sample_proof):
	"""
	Verify --verbose prints extra crypto details.
	"""
	mock_client.get_audit_proof.return_value = sample_proof

	with mock.patch('ambyte_cli.commands.audit.AuditVerifier') as mock_verifier:
		mock_verifier.compute_local_entry_hash.return_value = 'valid_hash_123'
		mock_verifier.verify_merkle_path.return_value = True
		mock_verifier.verify_block_signature.return_value = True

		result = runner.invoke(app, ['audit', 'verify', 'log-123', '--key', 'abc', '--verbose'])

	assert result.exit_code == 0
	assert 'Merkle Root:' in result.stdout
	assert 'root_hash' in result.stdout


# ==============================================================================
# TESTS: Audit List
# ==============================================================================


def test_list_logs_success(mock_client):
	"""
	Happy path: List logs, verifying table formatting.
	"""
	mock_logs = [
		{
			'id': 'uuid-1',
			'timestamp': '2025-01-01T12:00:00',
			'decision': 'ALLOW',
			'actor': {'id': 'alice'},
			'action': 'read',
			'block_id': 'sealed-block-id',  # Sealed
		},
		{
			'id': 'uuid-2',
			'timestamp': '2025-01-01T12:05:00',
			'decision': 'DENY',
			'actor': {'id': 'bob'},
			'action': 'write',
			'block_id': None,  # Buffered
		},
	]
	mock_client.list_audit_logs.return_value = mock_logs

	result = runner.invoke(app, ['audit', 'list'])

	assert result.exit_code == 0
	# Check Header
	assert 'Recent Audit Logs' in result.stdout
	# Check Row 1 (Sealed)
	assert 'uuid-1' in result.stdout
	assert 'ALLOW' in result.stdout
	assert '🔒 Sealed' in result.stdout
	# Check Row 2 (Buffered)
	assert 'uuid-2' in result.stdout
	assert 'DENY' in result.stdout
	assert '⏳ Buffered' in result.stdout


def test_list_logs_empty(mock_client):
	"""
	Scenario: API returns empty list.
	"""
	mock_client.list_audit_logs.return_value = []

	result = runner.invoke(app, ['audit', 'list'])

	assert result.exit_code == 0
	assert 'No audit logs found' in result.stdout


def test_list_logs_with_filters(mock_client):
	"""
	Verify CLI args are passed to the client method correctly.
	"""
	mock_client.list_audit_logs.return_value = []

	result = runner.invoke(app, ['audit', 'list', '--limit', '5', '--actor', 'dave'])

	assert result.exit_code == 0
	mock_client.list_audit_logs.assert_called_once_with(limit=5, actor='dave', resource=None)


def test_list_logs_api_error(mock_client):
	"""
	Scenario: API failure.
	"""
	mock_client.list_audit_logs.side_effect = Exception('Server Error')

	result = runner.invoke(app, ['audit', 'list'])

	assert result.exit_code == 1
	assert 'Failed to list logs' in result.stdout

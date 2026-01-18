import hashlib

import pytest
from ambyte_cli.services.audit_verifier import AuditVerifier
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# ==============================================================================
# TEST: Hashing (Content Integrity)
# ==============================================================================


def test_compute_local_entry_hash_determinism():
	"""
	Verify that dictionary key order does not affect the hash (Canonicalization).
	"""
	# Two dictionaries with same content but different key insertion order
	entry_1 = {
		'id': 'log-1',
		'action': 'read',
		'actor': {'id': 'alice'},
		'resource_urn': 'urn:test',
		'decision': 'ALLOW',
		'timestamp': '2025-01-01T00:00:00Z',
	}

	entry_2 = {
		'timestamp': '2025-01-01T00:00:00Z',
		'resource_urn': 'urn:test',
		'actor': {'id': 'alice'},
		'decision': 'ALLOW',
		'action': 'read',
		'id': 'log-1',
	}

	hash_1 = AuditVerifier.compute_local_entry_hash(entry_1)
	hash_2 = AuditVerifier.compute_local_entry_hash(entry_2)

	assert hash_1 == hash_2
	assert len(hash_1) == 64  # SHA-256 Hex Digest


def test_compute_local_entry_hash_value():
	"""
	Verify the actual hash value against a manual calculation.
	Ensures the serialization logic (separators, sorting) matches spec.
	"""
	entry = {
		'id': 'test-id',
		'timestamp': '2025-01-01T12:00:00Z',
		'actor': {'id': 'bob'},
		'resource_urn': 'urn:s3:bucket',
		'action': 'delete',
		'decision': 'DENY',
		'evaluation_trace': None,
		'request_context': {},
	}

	# Manual Canonical JSON generation:
	# 1. Sort keys
	# 2. No whitespace separators (',', ':')
	# 3. ensure_ascii=False
	expected_json_str = (
		'{"action":"delete","actor":{"id":"bob"},"decision":"DENY",'
		'"evaluation_trace":null,"id":"test-id","request_context":{},'
		'"resource_urn":"urn:s3:bucket","timestamp":"2025-01-01T12:00:00Z"}'
	)
	expected_bytes = expected_json_str.encode('utf-8')
	expected_hash = hashlib.sha256(expected_bytes).hexdigest()

	computed_hash = AuditVerifier.compute_local_entry_hash(entry)

	assert computed_hash == expected_hash


def test_compute_local_entry_hash_ignores_extra_fields():
	"""
	Verify that fields not in the canonical list (like 'entry_hash' or server metadata)
	are ignored during hash calculation.
	"""
	base_entry = {
		'id': '1',
		'timestamp': '2020-01-01',
		'actor': 'a',
		'resource_urn': 'r',
		'action': 'a',
		'decision': 'd',
	}

	# Entry with noise
	noisy_entry = base_entry.copy()
	noisy_entry['entry_hash'] = 'SHOULD_BE_IGNORED'
	noisy_entry['server_latency_ms'] = 50

	hash_base = AuditVerifier.compute_local_entry_hash(base_entry)
	hash_noisy = AuditVerifier.compute_local_entry_hash(noisy_entry)

	assert hash_base == hash_noisy


# ==============================================================================
# TEST: Merkle Verification (Inclusion Integrity)
# ==============================================================================


def test_verify_merkle_path_sorted_pairs():
	"""
	Verify the 'Sorted Pair' hashing strategy.
	Parent = SHA256( Min(A,B) + Max(A,B) )
	"""
	# Setup simple leaf hashes (hex strings)
	# "aaaa..." < "bbbb..."
	hash_a = 'a' * 64
	hash_b = 'b' * 64

	# Target is A, Sibling is B
	# Since A < B, Parent = Hash(A + B)
	combined_ab = bytes.fromhex(hash_a) + bytes.fromhex(hash_b)
	expected_root_ab = hashlib.sha256(combined_ab).hexdigest()

	# Case 1: Target is smaller than sibling
	assert AuditVerifier.verify_merkle_path(target_hash=hash_a, siblings=[hash_b], expected_root=expected_root_ab)

	# Case 2: Target is larger than sibling (Swap roles)
	# Target is B, Sibling is A
	# Since A < B, Parent is STILL Hash(A + B). Logic must sort them.
	assert AuditVerifier.verify_merkle_path(target_hash=hash_b, siblings=[hash_a], expected_root=expected_root_ab)


def test_verify_merkle_path_multi_level():
	"""
	Test a 2-level path.
	Leaf -> Parent -> Root
	"""
	# Level 0 (Leaves)
	h1 = '1' * 64
	h2 = '2' * 64
	h3 = '3' * 64
	h4 = '4' * 64

	# Level 1 (Parents)
	# p12 = Hash(h1 + h2) (since 1<2)
	p12_bytes = bytes.fromhex(h1) + bytes.fromhex(h2)
	p12 = hashlib.sha256(p12_bytes).hexdigest()

	# p34 = Hash(h3 + h4)
	p34_bytes = bytes.fromhex(h3) + bytes.fromhex(h4)
	p34 = hashlib.sha256(p34_bytes).hexdigest()

	# Level 2 (Root)
	# Ensure sorted order for root calculation. Let's assume p12 < p34 for this test data.
	# (Actually sha256 output is random, so we must check)
	if p12 < p34:
		root_bytes = bytes.fromhex(p12) + bytes.fromhex(p34)
	else:
		root_bytes = bytes.fromhex(p34) + bytes.fromhex(p12)
	root = hashlib.sha256(root_bytes).hexdigest()

	# Verify path for h1: Siblings are [h2, p34]
	assert AuditVerifier.verify_merkle_path(target_hash=h1, siblings=[h2, p34], expected_root=root)


def test_verify_merkle_path_failure():
	"""Ensure invalid paths return False."""
	h1 = 'a' * 64
	sibling = 'b' * 64
	fake_root = 'f' * 64  # Random mismatched root

	assert AuditVerifier.verify_merkle_path(h1, [sibling], fake_root) is False


# ==============================================================================
# TEST: Signature Verification (Authority Integrity)
# ==============================================================================


@pytest.fixture
def keypair():
	"""Generates a fresh Ed25519 keypair for testing."""
	private_key = ed25519.Ed25519PrivateKey.generate()
	public_key = private_key.public_key()

	# Export Public Key as Hex string (format used in CLI args)
	pub_bytes = public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
	pub_hex = pub_bytes.hex()

	return private_key, pub_hex


def test_verify_block_signature_valid(keypair):
	"""
	Test successful signature verification.
	"""
	private_key, public_key_hex = keypair

	# Mock Block Header Data
	header = {
		'sequence_index': 1,
		'prev_block_hash': 'prev_hash_hex',
		'merkle_root': 'root_hash_hex',
		'log_count': 100,
		'timestamp_end': '2025-01-01T12:00:00',
	}

	# 1. Replicate Signing Logic (from apps/audit-log/src/sealer.py)
	# Payload: "INDEX|PREV_HASH|ROOT|COUNT"
	payload_str = (
		f'{header["sequence_index"]}|{header["prev_block_hash"]}|{header["merkle_root"]}|{header["log_count"]}'
	)
	payload_bytes = payload_str.encode()

	signature = private_key.sign(payload_bytes)
	header['signature'] = signature.hex()

	# 2. Verify
	is_valid = AuditVerifier.verify_block_signature(header, public_key_hex)
	assert is_valid is True


def test_verify_block_signature_tampered_header(keypair):
	"""
	If header data (e.g. merkle root) doesn't match the signature, fail.
	"""
	private_key, public_key_hex = keypair

	# Sign original data
	payload = b'1|prev|root|10'
	sig = private_key.sign(payload)

	# Modify header presented to verifier
	header = {
		'sequence_index': 1,
		'prev_block_hash': 'prev',
		'merkle_root': 'TAMPERED_ROOT',  # Changed!
		'log_count': 10,
		'signature': sig.hex(),
	}

	is_valid = AuditVerifier.verify_block_signature(header, public_key_hex)
	assert is_valid is False


def test_verify_block_signature_wrong_key(keypair):
	"""
	If signed by a different private key, fail.
	"""
	_, public_key_hex = keypair
	rogue_private_key = ed25519.Ed25519PrivateKey.generate()

	# Sign with rogue key
	payload = b'1|prev|root|10'
	rogue_sig = rogue_private_key.sign(payload)

	header = {
		'sequence_index': 1,
		'prev_block_hash': 'prev',
		'merkle_root': 'root',
		'log_count': 10,
		'signature': rogue_sig.hex(),
	}

	# Verify against legitimate public key
	is_valid = AuditVerifier.verify_block_signature(header, public_key_hex)
	assert is_valid is False


def test_verify_block_signature_malformed_hex():
	"""
	If signature or key is not valid hex, handle gracefully (return False).
	"""
	header = {
		'sequence_index': 1,
		'prev_block_hash': 'p',
		'merkle_root': 'r',
		'log_count': 1,
		'signature': 'NOT_HEX_STRING',
	}
	# Public key is also invalid
	is_valid = AuditVerifier.verify_block_signature(header, 'ZZZZ')
	assert is_valid is False

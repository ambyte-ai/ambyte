import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class AuditVerifier:
	"""
	Client-side cryptographic verification logic.
	Replicates the hashing and tree construction logic of the Control Plane
	to independently validate audit proofs.
	"""

	@staticmethod
	def compute_local_entry_hash(entry_dict: dict[str, Any]) -> str:
		"""
		Re-calculates the SHA-256 hash of a log entry to ensure fields haven't been tampered with.
		Must match apps/audit-log/src/hashing.py logic EXACTLY.
		"""
		# 1. Create a clean dictionary of fields 1-8 (exclude entry_hash and system fields)
		# We assume the input dict comes from the API JSON response
		clean_payload = {
			'id': entry_dict['id'],
			'timestamp': entry_dict['timestamp'],
			'actor': entry_dict['actor'],
			'resource_urn': entry_dict['resource_urn'],
			'action': entry_dict['action'],
			'decision': entry_dict['decision'],
			'evaluation_trace': entry_dict.get('evaluation_trace'),
			'request_context': entry_dict.get('request_context', {}),
		}

		# 2. Canonicalize
		# sort_keys=True, separators=(',', ':') removes whitespace
		try:
			canonical_bytes = json.dumps(
				clean_payload,
				sort_keys=True,
				separators=(',', ':'),
				ensure_ascii=False,
			).encode('utf-8')
		except Exception as e:
			raise ValueError(f'Failed to serialize entry for verification: {e}') from e

		# 3. Hash
		return hashlib.sha256(canonical_bytes).hexdigest()

	@staticmethod
	def verify_merkle_path(target_hash: str, siblings: list[str], expected_root: str) -> bool:
		"""
		Walks the Merkle path from the leaf to the root using Sorted Pair hashing.
		"""
		current_hash = target_hash

		for sibling in siblings:
			a_bytes = bytes.fromhex(current_hash)
			b_bytes = bytes.fromhex(sibling)

			# Sorted Pair Strategy (Lexicographical sort before hash)
			if a_bytes < b_bytes:
				combined = a_bytes + b_bytes
			else:
				combined = b_bytes + a_bytes

			current_hash = hashlib.sha256(combined).hexdigest()

		return current_hash == expected_root

	@staticmethod
	def verify_block_signature(header: dict[str, Any], public_key_hex: str) -> bool:
		"""
		Verifies the digital signature of the Block Header using the System Public Key.

		Payload Format (from Sealer): "INDEX|PREV_HASH|ROOT|COUNT"
		Algorithm: Ed25519
		"""
		try:
			# 1. Reconstruct the signing payload
			# Ensure types match the sealer's expectation
			idx = header['sequence_index']
			prev = header['prev_block_hash']
			root = header['merkle_root']
			count = header['log_count']

			payload = f'{idx}|{prev}|{root}|{count}'.encode()

			# 2. Decode Hex
			sig_bytes = bytes.fromhex(header['signature'])
			pub_bytes = bytes.fromhex(public_key_hex)

			# 3. Verify
			public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
			public_key.verify(sig_bytes, payload)

			return True
		except (ValueError, InvalidSignature, KeyError):
			# Log error if needed, but return False to indicate verification failure
			return False

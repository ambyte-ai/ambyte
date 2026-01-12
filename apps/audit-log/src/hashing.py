import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID


class CanonicalJSONEncoder(json.JSONEncoder):
	"""
	Ensures deterministic serialization of complex types for cryptographic hashing.
	"""

	def default(self, o: Any) -> Any:
		if isinstance(o, (datetime, date)):
			# ISO 8601 is the standard.
			# We assume UTC if tzinfo is present, or naive strings.
			return o.isoformat()
		if isinstance(o, UUID):
			return str(o)
		if isinstance(o, Enum):
			return o.value
		if isinstance(o, set):
			# Sets are unordered, so we convert to a sorted list
			return sorted(o)
		return super().default(o)


def compute_entry_hash(data: dict[str, Any]) -> str:
	"""
	Computes the SHA-256 hash of a log entry dictionary.

	The process is:
	1. Create a shallow copy to avoid mutating the input.
	2. Remove 'entry_hash' if present (we don't hash the hash).
	3. Serialize to Minified Canonical JSON (sorted keys, no whitespace).
	4. Compute SHA-256.

	Args:
	    data: The dictionary representing an AuditLogEntry.

	Returns:
	    A 64-character hexadecimal string.
	"""  # noqa: E101
	# 1. Clean Payload
	# We strip the field we are about to calculate to ensure idempotency.
	payload = data.copy()
	payload.pop('entry_hash', None)

	# 2. Canonicalize
	# sort_keys=True: Deterministic ordering (a, b, c...)
	# separators=(',', ':'): Removes whitespace for compact representation
	try:
		canonical_bytes = json.dumps(
			payload,
			cls=CanonicalJSONEncoder,
			sort_keys=True,
			separators=(',', ':'),
			ensure_ascii=False,
		).encode('utf-8')
	except (TypeError, ValueError) as e:
		# Serialization failure is a critical security/integrity risk.
		# We must raise to prevent processing invalid data.
		raise ValueError(f'Failed to serialize log entry for hashing: {e}') from e

	# 3. Hash
	return hashlib.sha256(canonical_bytes).hexdigest()

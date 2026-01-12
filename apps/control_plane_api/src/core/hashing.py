import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID


class CanonicalJSONEncoder(json.JSONEncoder):
	"""
	Ensures deterministic serialization of complex types for cryptographic hashing.
	Matches logic in apps/audit-log/src/hashing.py.
	"""

	def default(self, o: Any) -> Any:
		if isinstance(o, (datetime, date)):
			# ISO 8601 UTC or naive
			return o.isoformat()
		if isinstance(o, UUID):
			return str(o)
		if isinstance(o, Enum):
			return o.value
		if isinstance(o, set):
			return sorted(o)
		return super().default(o)


def compute_entry_hash(data: dict[str, Any]) -> str:
	"""
	Computes the SHA-256 hash of a log entry dictionary.

	1. Removes 'entry_hash' to prevent circular logic.
	2. Sorts keys and removes whitespace for canonicalization.
	3. Hashes the result.
	"""
	# 1. Clean Payload
	payload = data.copy()
	payload.pop('entry_hash', None)

	# 2. Canonicalize
	try:
		canonical_bytes = json.dumps(
			payload,
			cls=CanonicalJSONEncoder,
			sort_keys=True,
			separators=(',', ':'),
			ensure_ascii=False,
		).encode('utf-8')
	except (TypeError, ValueError) as e:
		# In a synchronous API path, we raise to alert the caller
		raise ValueError(f'Failed to serialize log entry for hashing: {e}') from e

	# 3. Hash
	return hashlib.sha256(canonical_bytes).hexdigest()

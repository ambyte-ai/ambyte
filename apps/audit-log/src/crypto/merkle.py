import hashlib


class MerkleTree:
	"""
	A Merkle Tree implementation using SHA-256.

	Strategy: Sorted Pairs.
	When combining two nodes (leaves or internal), they are sorted lexicographically
	before hashing. This simplifies proof verification as the proof does not need
	to carry positional metadata (Left/Right), only the sibling hashes.

	Structure:
	- Leaves are pre-hashed (SHA-256 hex strings) provided by the caller.
	- If a level has an odd number of nodes, the last node is paired with itself.
	"""

	def __init__(self, leaves: list[str]):
		"""
		Args:
		    leaves: A list of hex-encoded SHA-256 strings.
		            These are typically the 'entry_hash' from AuditLogEntry.
		"""  # noqa: E101
		# We perform an initial sort of the leaves to ensure the tree structure
		# is deterministic regardless of the insertion order in the database batch.
		self.leaves = sorted(leaves)
		# Optimization: Map hash to index for O(1) lookup during proof generation
		self.leaf_to_index = {h: i for i, h in enumerate(self.leaves)}
		self.levels: list[list[str]] = []
		self.root: str = ''

		if self.leaves:
			self._build()

	def _hash_pair(self, left_hex: str, right_hex: str) -> str:
		"""
		Hashes two hex strings together using the Sorted Pair strategy.
		H = SHA256( Min(A,B) + Max(A,B) )
		"""
		# Convert hex to bytes
		a_bytes = bytes.fromhex(left_hex)
		b_bytes = bytes.fromhex(right_hex)

		# Sort for determinism
		if a_bytes < b_bytes:
			combined = a_bytes + b_bytes
		else:
			combined = b_bytes + a_bytes

		return hashlib.sha256(combined).hexdigest()

	def _build(self):
		"""
		Constructs the tree bottom-up.
		Populates self.levels and self.root.
		"""
		current_level = self.leaves
		self.levels.append(current_level)

		while len(current_level) > 1:
			next_level = []

			for i in range(0, len(current_level), 2):
				left = current_level[i]

				# Handle odd number of nodes by duplicating the last one
				if i + 1 < len(current_level):
					right = current_level[i + 1]
				else:
					right = left

				parent_hash = self._hash_pair(left, right)
				next_level.append(parent_hash)

			self.levels.append(next_level)
			current_level = next_level

		# The last remaining item is the root
		self.root = current_level[0]

	def get_root(self) -> str:
		"""Returns the Hex SHA-256 Merkle Root."""
		return self.root

	def get_proof(self, target_hash: str) -> list[str]:
		"""
		Generates the inclusion proof (audit path) for a specific leaf hash.

		Args:
		    target_hash: The leaf hash to prove.

		Returns:
		    A list of sibling hashes required to reconstruct the root.
		    Returns empty list if target_hash is not in the tree.
		"""  # noqa: E101
		# 1. Fast Lookup: Find index of the leaf
		idx = self.leaf_to_index.get(target_hash)
		if idx is None:
			return []

		proof = []

		# 2. Traverse up the tree levels (excluding the root level)
		for level in self.levels[:-1]:
			# Identify the sibling index using XOR
			# If idx is even (0), sibling is Right (1) -> 0^1 = 1
			# If idx is odd (1), sibling is Left (0)  -> 1^1 = 0
			sibling_idx = idx ^ 1

			# Handle the odd-node-at-end case
			if sibling_idx < len(level):
				sibling_hash = level[sibling_idx]
			else:
				# If we are the last odd node, we were paired with ourselves
				sibling_hash = level[idx]

			proof.append(sibling_hash)

			# Move up to the parent index (integer division by 2)
			idx //= 2

		return proof

	@staticmethod
	def verify(target_hash: str, proof: list[str], root_hash: str) -> bool:
		"""
		Static helper to verify a proof against a known root.

		This duplicates the logic used by the CLI 'verify' command.
		"""
		current_hash = target_hash

		for sibling_hash in proof:
			# Reconstruct the parent using the Sorted Pair strategy
			a_bytes = bytes.fromhex(current_hash)
			b_bytes = bytes.fromhex(sibling_hash)

			if a_bytes < b_bytes:
				combined = a_bytes + b_bytes
			else:
				combined = b_bytes + a_bytes

			current_hash = hashlib.sha256(combined).hexdigest()

		return current_hash == root_hash

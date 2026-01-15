import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from src.config import settings

logger = logging.getLogger(__name__)


class AuditSigner:
	"""
	Manages the System Private Key for digitally signing Audit Blocks.

	Algorithm: Ed25519 (Edwards-curve Digital Signature Algorithm).
	Format: Keys and Signatures are exchanged as Hexadecimal strings.
	"""

	def __init__(self, private_key_hex: str | None = None):
		"""
		Initialize the signer.

		Args:
		    private_key_hex: A 32-byte private key encoded as a hex string.
		                     If None, it looks in settings.AMBYTE_SYSTEM_PRIVATE_KEY.
		                     If that is also None, it generates an ephemeral key (DEV only).
		"""  # noqa: E101
		self._private_key: ed25519.Ed25519PrivateKey

		# 1. Try Argument
		key_data = private_key_hex

		# 2. Try Settings (Env Var)
		# Note: You need to add AMBYTE_SYSTEM_PRIVATE_KEY to src/config.py settings model
		if not key_data and hasattr(settings, 'SYSTEM_PRIVATE_KEY'):
			key_data = settings.SYSTEM_PRIVATE_KEY

		if key_data:
			try:
				# Load persistent key
				raw_bytes = bytes.fromhex(key_data)
				self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw_bytes)
				logger.info('Loaded persistent System Private Key.')
			except Exception as e:
				logger.critical(f'Failed to load System Private Key: {e}')
				raise ValueError('Invalid Private Key format') from e
		else:
			# 3. Generate Ephemeral (Dev Mode)
			# WARNING: Restarting the container will break the hash chain validation
			# for previously signed blocks because the public key will change.
			logger.warning(
				'⚠️  NO SYSTEM PRIVATE KEY FOUND! Generating an ephemeral key. '
				'Audit chains will be unverifiable after restart. '
				'Set AMBYTE_SYSTEM_PRIVATE_KEY in production.'
			)
			self._private_key = ed25519.Ed25519PrivateKey.generate()

		# Cache public key for fast access
		self._public_key = self._private_key.public_key()

	def sign(self, data: bytes) -> str:
		"""
		Cryptographically signs the data.

		Args:
		    data: The raw bytes to sign (usually the canonical string of the Block Header).

		Returns:
		    The signature as a Hexadecimal string.
		"""  # noqa: E101
		signature_bytes = self._private_key.sign(data)
		return signature_bytes.hex()

	def get_public_key_hex(self) -> str:
		"""
		Returns the Public Key in Hex format.
		This key is required by the CLI/API to verify the 'AuditProof'.
		"""
		pub_bytes = self._public_key.public_bytes(
			encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
		)
		return pub_bytes.hex()

	def get_private_key_hex_unsafe(self) -> str:
		"""
		Export private key as hex.
		Useful ONLY for printing the generated ephemeral key in logs during dev/setup.
		"""
		priv_bytes = self._private_key.private_bytes(
			encoding=serialization.Encoding.Raw,
			format=serialization.PrivateFormat.Raw,
			encryption_algorithm=serialization.NoEncryption(),
		)
		return priv_bytes.hex()

	@staticmethod
	def verify(data: bytes, signature_hex: str, public_key_hex: str) -> bool:
		"""
		Static utility to verify a signature.
		Used by the verification CLI tools.
		"""
		try:
			pub_bytes = bytes.fromhex(public_key_hex)
			sig_bytes = bytes.fromhex(signature_hex)

			public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
			public_key.verify(sig_bytes, data)
			return True
		except (ValueError, InvalidSignature):
			return False

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# 1. Generate Key
private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# 2. Serialize to Hex
priv_hex = private_key.private_bytes(
	encoding=serialization.Encoding.Raw,
	format=serialization.PrivateFormat.Raw,
	encryption_algorithm=serialization.NoEncryption(),
).hex()

pub_hex = public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex()

print(f'PRIVATE KEY (Set AMBYTE_AUDIT_SYSTEM_PRIVATE_KEY): {priv_hex}')
print(f'PUBLIC KEY  (Give to Users / CLI):                 {pub_hex}')

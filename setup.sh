#!/bin/bash
set -e

echo "🚀 Setting up Ambyte environment..."

if [ ! -f .env ]; then
  echo "=> Copying .env.example to .env..."
  cp .env.example .env
else
  echo "=> .env already exists. It will be updated."
fi

# Ensure uv is available to use the project's python environment
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first: https://docs.astral.sh/uv/"
    exit 1
fi

echo "=> Generating cryptographic keys via Python..."

# We use uv run to execute python in the context of the project, 
# ensuring the 'cryptography' library is available.
uv run python -c "
import secrets
import re
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# 1. Generate keys
secret_key = secrets.token_urlsafe(32)
ingest_worker_key = f'sk_ingest_{secrets.token_hex(16)}'

priv = ed25519.Ed25519PrivateKey.generate()
priv_hex = priv.private_bytes(
    encoding=serialization.Encoding.Raw, 
    format=serialization.PrivateFormat.Raw, 
    encryption_algorithm=serialization.NoEncryption()
).hex()
pub_hex = priv.public_key().public_bytes(
    encoding=serialization.Encoding.Raw, 
    format=serialization.PublicFormat.Raw
).hex()

# 2. Read existing .env
try:
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
except FileNotFoundError:
    content = ''

def set_env(key, value, text):
    if re.search(rf'^{key}=.*', text, re.MULTILINE):
        return re.sub(rf'^{key}=.*', f'{key}={value}', text, flags=re.MULTILINE)
    else:
        return text + f'\n{key}={value}\n'

# 3. Inject new keys
content = set_env('SECRET_KEY', secret_key, content)
content = set_env('INGEST_WORKER_API_KEY', ingest_worker_key, content)
content = set_env('AMBYTE_AUDIT_SYSTEM_PRIVATE_KEY', priv_hex, content)
content = set_env('AMBYTE_SYSTEM_PUBLIC_KEY', pub_hex, content)

# 4. Save
with open('.env', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'''✅ Keys generated and securely injected into .env:
   - SECRET_KEY
   - INGEST_WORKER_API_KEY
   - AMBYTE_AUDIT_SYSTEM_PRIVATE_KEY
   - AMBYTE_SYSTEM_PUBLIC_KEY: {pub_hex}
''')
"

echo "🎉 Setup complete! You're ready to start the application."

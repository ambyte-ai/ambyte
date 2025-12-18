import hashlib
import secrets
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from src.core.config import settings

# ==============================================================================
# API Key Logic (Machine Auth - High Performance)
# ==============================================================================
# Used by SDKs, CLI, and Airflow.


def generate_api_key(prefix: str = 'sk_live_') -> tuple[str, str]:
	"""
	Generates a new secure API Key.
	Returns: (raw_key, key_hash)
	"""
	random_part = secrets.token_urlsafe(32)
	raw_key = f'{prefix}{random_part}'
	key_hash = hash_token(raw_key)
	return raw_key, key_hash


def hash_token(token: str) -> str:
	"""Calculates the SHA-256 hash of a raw token."""
	return hashlib.sha256(token.encode()).hexdigest()


def verify_token(plain_token: str, hashed_token: str) -> bool:
	"""Constant-time comparison for API keys."""
	computed_hash = hash_token(plain_token)
	return secrets.compare_digest(computed_hash, hashed_token)


# ==============================================================================
# Clerk JWT Logic (Human Auth)
# ==============================================================================

# Simple in-memory cache for the Public Keys (JWKS) to avoid HTTP hits on every request.
# Structure: { "kid_123": { ...key_data... } }
_JWKS_CACHE: dict[str, Any] = {}


async def _get_clerk_jwks() -> dict[str, Any]:
	"""
	Fetches the JSON Web Key Set from Clerk.
	Populates the global cache.
	"""
	global _JWKS_CACHE

	# If cache is empty, fetch.
	# TODO: In production, add a TTL or refresh logic if verification fails.
	if not _JWKS_CACHE:
		async with httpx.AsyncClient() as client:
			response = await client.get(settings.CLERK_JWKS_URL)
			response.raise_for_status()
			jwks = response.json()

			# Index by Key ID (kid) for O(1) lookup
			for key in jwks.get('keys', []):
				_JWKS_CACHE[key['kid']] = key

	return _JWKS_CACHE


async def verify_clerk_token(token: str) -> dict[str, Any] | None:
	"""
	Verifies a Clerk JWT against the fetched JWKS.

	Returns:
	    dict: The decoded claims (sub, email, exp, etc.)
	    None: If invalid or expired.
	"""
	try:
		# 1. Decode Headers to find which Key ID (kid) signed this token
		headers = jwt.get_unverified_header(token)
		kid = headers.get('kid')
		if not kid:
			return None

		# 2. Get the Public Key
		jwks = await _get_clerk_jwks()
		public_key = jwks.get(kid)

		# If key not found, try refreshing cache once (key rotation scenario)
		if not public_key:
			_JWKS_CACHE.clear()
			jwks = await _get_clerk_jwks()
			public_key = jwks.get(kid)

		if not public_key:
			return None

		# 3. Verify Signature
		payload = jwt.decode(
			token,
			public_key,
			algorithms=['RS256'],
			audience=settings.CLERK_AUDIENCE,  # Optional check
			issuer=settings.CLERK_ISSUER,  # Mandatory check
			options={'verify_at_hash': False, 'verify_aud': settings.CLERK_AUDIENCE is not None},
		)
		return payload

	except (ExpiredSignatureError, JWTClaimsError, JWTError, httpx.HTTPError):
		# In a real app, you might log specific errors here TODO
		return None
	except Exception:
		return None

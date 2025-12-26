import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
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

logger = logging.getLogger(__name__)

# JWKS Cache Configuration
JWKS_CACHE_KEY = 'clerk:jwks'
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour

# Fallback in-memory cache (used when Redis is unavailable)
_JWKS_MEMORY_CACHE: dict[str, Any] = {}
_JWKS_CACHE_EXPIRY: datetime | None = None


async def _get_clerk_jwks() -> dict[str, Any]:
	"""
	Fetches the JSON Web Key Set from Clerk.
	Uses Redis cache with TTL, falls back to in-memory cache if Redis unavailable.
	"""
	global _JWKS_MEMORY_CACHE, _JWKS_CACHE_EXPIRY

	# Try Redis cache first
	try:
		from src.core.cache import cache

		if cache._redis:
			cached_data = await cache._redis.get(JWKS_CACHE_KEY)
			if cached_data:
				# Parse cached JWKS and index by kid
				jwks_data = json.loads(cached_data)
				return {key['kid']: key for key in jwks_data.get('keys', [])}
	except Exception as e:
		logger.debug(f'Redis cache unavailable for JWKS: {e}')

	# Check in-memory cache with TTL
	now = datetime.now(timezone.utc)
	if _JWKS_MEMORY_CACHE and _JWKS_CACHE_EXPIRY and now < _JWKS_CACHE_EXPIRY:
		return _JWKS_MEMORY_CACHE

	# Fetch fresh JWKS from Clerk
	async with httpx.AsyncClient() as client:
		response = await client.get(settings.CLERK_JWKS_URL)
		response.raise_for_status()
		jwks = response.json()

	# Index by Key ID (kid) for O(1) lookup
	indexed_jwks = {key['kid']: key for key in jwks.get('keys', [])}

	# Store in Redis (if available)
	try:
		from src.core.cache import cache

		if cache._redis:
			await cache._redis.set(JWKS_CACHE_KEY, json.dumps(jwks), ex=JWKS_CACHE_TTL_SECONDS)
	except Exception as e:
		logger.debug(f'Failed to cache JWKS in Redis: {e}')

	# Always update in-memory cache as fallback
	_JWKS_MEMORY_CACHE = indexed_jwks
	_JWKS_CACHE_EXPIRY = datetime.now(timezone.utc).replace(
		second=datetime.now(timezone.utc).second + JWKS_CACHE_TTL_SECONDS
	)

	return indexed_jwks


async def _refresh_jwks_cache() -> dict[str, Any]:
	"""Force refresh the JWKS cache (used on key rotation)."""
	global _JWKS_MEMORY_CACHE, _JWKS_CACHE_EXPIRY

	# Clear Redis cache
	try:
		from src.core.cache import cache

		if cache._redis:
			await cache._redis.delete(JWKS_CACHE_KEY)
	except Exception as e:
		logger.debug(f'Failed to clear Redis JWKS cache: {e}')

	# Clear in-memory cache
	_JWKS_MEMORY_CACHE = {}
	_JWKS_CACHE_EXPIRY = None

	# Fetch fresh
	return await _get_clerk_jwks()


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
			logger.info(f'JWKS key {kid} not found, refreshing cache (possible key rotation)')
			jwks = await _refresh_jwks_cache()
			public_key = jwks.get(kid)

		if not public_key:
			logger.warning(f'JWKS key {kid} not found even after refresh')
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

	except ExpiredSignatureError:
		logger.debug('JWT verification failed: Token expired')
		return None
	except JWTClaimsError as e:
		logger.debug(f'JWT verification failed: Invalid claims - {e}')
		return None
	except JWTError as e:
		logger.debug(f'JWT verification failed: {e}')
		return None
	except httpx.HTTPError as e:
		logger.warning(f'JWT verification failed: HTTP error fetching JWKS - {e}')
		return None
	except Exception as e:
		logger.error(f'JWT verification failed: Unexpected error - {e}')
		return None

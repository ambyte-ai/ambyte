import logging
import time
from typing import Any, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ambyte.config import AmbyteMode, get_config
from ambyte.context import get_current_actor, get_current_run_id, get_extra_context
from ambyte.exceptions import AmbyteConnectionError

# Setup SDK Logger
logger = logging.getLogger('ambyte')


class AmbyteClient:
	"""
	The main entry point for interacting with the Ambyte Control Plane.
	Maintains persistent HTTP connections and handles fail-over logic.
	"""

	_instance: Optional['AmbyteClient'] = None

	def __init__(self):
		self.settings = get_config()

		# Headers for all requests
		self._headers = {
			'Authorization': f'Bearer {self.settings.api_key_value}',
			'X-Ambyte-Service': self.settings.service_name,
			'User-Agent': 'ambyte-python-sdk/0.1.0',
		}

		# Sync Client (for standard blocking code)
		self._client = httpx.Client(
			base_url=str(self.settings.control_plane_url),
			headers=self._headers,
			timeout=5.0,  # Strict timeout to avoid blocking pipelines
		)

		# Async Client (for async/await code)
		self._async_client = httpx.AsyncClient(
			base_url=str(self.settings.control_plane_url), headers=self._headers, timeout=5.0
		)

	@classmethod
	def get_instance(cls) -> 'AmbyteClient':
		"""Singleton Accessor"""
		if cls._instance is None:
			cls._instance = AmbyteClient()
		return cls._instance

	def close(self):
		"""Cleanup resources."""
		self._client.close()
		# Async client needs await to close properly, strictly speaking,
		# but for clean shutdown scripts we can attempt synchronous close or rely on GC.
		try:
			import asyncio

			asyncio.create_task(self._async_client.aclose())
		except Exception:
			pass

	# ==========================================================================
	# INTERNAL HELPERS
	# ==========================================================================

	def _should_bypass(self) -> bool:
		"""
		Check if we should skip the network call entirely.
		"""
		if self.settings.mode == AmbyteMode.OFF:
			return True
		return False

	def _handle_connection_error(self, e: Exception) -> bool:
		"""
		Decides whether to raise an exception or fail-open (return True).
		"""
		msg = f'Failed to connect to Ambyte Control Plane: {str(e)}'

		if self.settings.fail_open:
			logger.warning(f'{msg} - FAILING OPEN (Access Allowed).')  # pylint: disable=logging-fstring-interpolation
			return True
		logger.error(f'{msg} - FAILING CLOSED (Access Denied).')  # pylint: disable=logging-fstring-interpolation
		raise AmbyteConnectionError(msg) from e

	def _build_check_payload(
		self,
		resource_urn: str,
		action: str,
		actor_id: Optional[str],
		context: Optional[dict[str, Any]],
	) -> dict[str, Any]:
		"""
		Constructs the request payload by merging explicit arguments
		with implicit ContextVars.
		"""
		# 1. Resolve Actor ID
		final_actor_id = actor_id
		if not final_actor_id:
			ctx_actor = get_current_actor()
			if ctx_actor:
				final_actor_id = ctx_actor.id

		# Default to anonymous if neither arg nor context is present
		if not final_actor_id:
			final_actor_id = 'anonymous'

		# 2. Resolve Context Attributes
		# Start with extras from ContextVars
		final_context = get_extra_context().copy()
		# Overlay explicit argument context
		if context:
			final_context.update(context)

		# 3. Add Run ID automatically (useful for temporal policy logic)
		run_id = get_current_run_id()
		if run_id:
			final_context['run_id'] = run_id

		return {
			'resource_urn': resource_urn,
			'action': action,
			'actor_id': final_actor_id,
			'context': final_context,
		}

	# ==========================================================================
	# PERMISSION CHECKS (SYNC)
	# ==========================================================================

	@retry(
		retry=retry_if_exception_type(
			httpx.HTTPStatusError
		),  # Only retry 5xx errors, not connection errors immediately
		stop=stop_after_attempt(3),
		wait=wait_exponential(multiplier=1, min=2, max=10),
		reraise=True,
	)
	def check_permission(
		self,
		resource_urn: str,
		action: str,
		actor_id: Optional[str] = None,
		context: Optional[dict[str, Any]] = None,
	) -> bool:
		"""
		Blocking call to check if an action is allowed.
		Autofills actor_id and context from ambyte.context if not provided.
		"""
		if self._should_bypass():
			return True

		payload = self._build_check_payload(resource_urn, action, actor_id, context)

		try:
			response = self._client.post('/v1/check', json=payload)
			response.raise_for_status()

			# Expecting API format: {"result": "ALLOW" | "DENY", ...}
			data = response.json()
			return data.get('result') == 'ALLOW'

		except httpx.HTTPError as e:
			return self._handle_connection_error(e)

	# ==========================================================================
	# PERMISSION CHECKS (ASYNC)
	# ==========================================================================

	@retry(
		retry=retry_if_exception_type(httpx.HTTPStatusError),
		stop=stop_after_attempt(3),
		wait=wait_exponential(multiplier=1, min=2, max=10),
		reraise=True,
	)
	async def check_permission_async(
		self, resource_urn: str, action: str, actor_id: Optional[str] = None, context: Optional[dict[str, Any]] = None
	) -> bool:
		"""
		Non-blocking (Async/Await) permission check.
		"""
		if self._should_bypass():
			return True

		payload = {
			'resource_urn': resource_urn,
			'action': action,
			'actor_id': actor_id or 'anonymous',
			'context': context or {},
		}

		try:
			response = await self._async_client.post('/v1/check', json=payload)
			response.raise_for_status()
			data = response.json()
			return data.get('result') == 'ALLOW'

		except httpx.HTTPError as e:
			return self._handle_connection_error(e)

	# ==========================================================================
	# AUDIT LOGGING
	# ==========================================================================

	def log_access(self, resource_urn: str, action: str, allowed: bool, actor_id: Optional[str] = None):
		"""
		Fire-and-forget audit log.
		In a real implementation, this should push to a background queue
		to avoid blocking the main thread. For MVP, we send simple HTTP.
		"""
		if self.settings.mode == AmbyteMode.OFF:
			return

		payload = {
			'timestamp': time.time(),
			'resource_urn': resource_urn,
			'action': action,
			'allowed': allowed,
			'actor_id': actor_id or 'anonymous',
		}

		# MVP: Fire synchronous call inside a try/except to never crash execution
		# Future: Move to BackgroundTask or Producer/Consumer Queue
		try:
			self._client.post('/v1/audit', json=payload)
		except Exception as e:
			# Never fail an application because logging failed
			logger.warning(f'Failed to emit audit log: {e}')  # pylint: disable=logging-fstring-interpolation


# Helper for external usage
def get_client() -> AmbyteClient:
	return AmbyteClient.get_instance()

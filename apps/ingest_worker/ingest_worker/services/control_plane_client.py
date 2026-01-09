import logging
from typing import Any

import httpx
from ambyte_schemas.models.obligation import Obligation
from ingest_worker.config import settings
from tenacity import (
	retry,
	retry_if_exception,
	stop_after_attempt,
	wait_exponential,
)

logger = logging.getLogger(__name__)


class ControlPlaneClient:
	"""
	Internal client for pushing extracted policies to the Ambyte API.
	Uses the System API Key.
	"""

	def __init__(self):
		base_url = str(settings.CONTROL_PLANE_URL).rstrip('/')
		api_key = settings.CONTROL_PLANE_API_KEY

		token = api_key.get_secret_value() if hasattr(api_key, 'get_secret_value') else str(api_key)

		self.client = httpx.AsyncClient(
			base_url=base_url,
			timeout=30.0,
			headers={
				'Authorization': f'Bearer {token}',
				'User-Agent': 'ambyte-ingest-worker/0.1.0',
				'Content-Type': 'application/json',
			},
		)

	async def close(self):
		"""Clean up the connection pool."""
		await self.client.aclose()

	@staticmethod
	def _should_retry_predicate(exception: BaseException) -> bool:
		"""
		Retry predicate:
		- Retry on Network Errors (DNS, Timeout).
		- Retry on Server Errors (500, 502, 503, 504).
		- Do NOT retry on Client Errors (400, 401, 403, 422) - these indicate logic/schema bugs.
		"""
		if isinstance(exception, (httpx.NetworkError, httpx.TimeoutException)):
			return True

		if isinstance(exception, httpx.HTTPStatusError):
			# Retry 5xx errors, fail fast on 4xx
			return exception.response.status_code >= 500

		return False

	@retry(
		retry=retry_if_exception(lambda exc: ControlPlaneClient._should_retry_predicate(exc)),
		stop=stop_after_attempt(5),
		wait=wait_exponential(multiplier=1, min=2, max=30),
		reraise=True,
	)
	async def push_obligations(self, project_id: str, obligations: list[Obligation]) -> list[dict[str, Any]]:
		"""
		Sends the extracted obligations to the Control Plane for persistence.

		Args:
		    project_id: The UUID of the tenant project.
		    obligations: List of Pydantic Obligation models.

		Returns:
		    The JSON response from the API (list of upserted items).
		"""  # noqa: E101
		if not obligations:
			logger.info('No obligations to sync.')
			return []

		# 1. Serialize Pydantic Models
		# We must use model_dump(mode='json') to ensure nested objects (enums, dates)
		# are converted to primitives compatible with JSON serialization.
		payload_data = [ob.model_dump(mode='json', exclude_none=True) for ob in obligations]

		# 2. Construct API Payload (BatchObligationCreate schema)
		body = {
			'obligations': payload_data,
			'prune': False,  # Worker is additive; never delete existing policies
			'dry_run': False,
		}

		# 3. Request
		# We inject the Project ID header here to context-switch the API
		logger.info(f'Pushing {len(obligations)} obligations to Project {project_id}...')

		response = await self.client.put('/v1/obligations/', json=body, headers={'X-Ambyte-Project-Id': project_id})

		# 4. Error Handling
		if response.is_error:
			if response.status_code == 422:
				logger.error(f'Schema Validation Error from Control Plane: {response.text}')
			elif response.status_code == 403:
				logger.error(f'Permission Denied. Check System API Key scopes. Response: {response.text}')

			# Raise exception to trigger retry logic (if 5xx) or fail job (if 4xx)
			response.raise_for_status()

		logger.info('Successfully synced obligations to Control Plane.')
		return response.json()

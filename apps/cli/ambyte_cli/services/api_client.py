"""
Cloud API Client for management operations (Push, Pull, Inventory Sync).
Unlike the high-performance SDK client, this focuses on administrative
consistency and detailed error reporting for the CLI.
"""

import logging

import httpx
from ambyte_cli.config import AmbyteConfig
from ambyte_cli.services.auth import CredentialsManager
from ambyte_cli.ui.console import console

logger = logging.getLogger(__name__)


class CloudApiClient:
	"""
	Client for interacting with the Ambyte Control Plane Management API.
	"""

	def __init__(self, config: AmbyteConfig):
		self.config = config
		self.auth = CredentialsManager()
		self.base_url = str(config.cloud.url).rstrip('/')

		# Initialize the sync client with default timeouts
		self._client = httpx.Client(
			base_url=self.base_url,
			timeout=30.0,  # Management ops like push/pull can be heavier
			headers=self._get_headers(),
		)

	def _get_headers(self) -> dict:
		"""
		Retrieves the API key and constructs authorization headers.
		"""
		api_key = self.auth.get_api_key()
		if not api_key:
			return {}

		return {
			'Authorization': f'Bearer {api_key}',
			'Content-Type': 'application/json',
			'X-Ambyte-Project-Id': self.config.cloud.project_id or '',
			'User-Agent': 'ambyte-cli/0.1.0',
		}

	def _handle_http_error(self, e: httpx.HTTPStatusError):
		"""
		Pretty-prints API errors to the console.
		"""
		status_code = e.response.status_code
		try:
			detail = e.response.json().get('detail', e.response.text)
		except Exception:
			detail = e.response.text

		if status_code == 401:
			console.print(
				'[error]Authentication Failed:[/error] Your API key is invalid or expired. '
				'Run [cyan]ambyte login[/cyan].'
			)
		elif status_code == 403:
			console.print(f'[error]Permission Denied:[/error] {detail}')
		elif status_code == 404:
			console.print('[error]Resource Not Found:[/error] Check your Project ID in .ambyte/config.yaml')
		else:
			console.print(f'[error]Cloud Error ({status_code}):[/error] {detail}')

	def push_obligations(self, obligations_data: list[dict], prune: bool = False, dry_run: bool = False) -> list[dict]:
		"""
		Sends a batch of obligations to the Control Plane for upsert.

		Args:
			obligations_data: A list of dicts serialized from Obligation schemas.
			prune: If True, deactivates obligations not present in this batch.
			dry_run: If True, simulates the operation without persisting changes.
		Returns:
			The list of successfully processed obligations from the server.
		"""  # noqa: E101
		payload = {'obligations': obligations_data, 'prune': prune, 'dry_run': dry_run}

		try:
			# We use PUT as defined in the API for bulk upsert (idempotent)
			response = self._client.put('/v1/obligations/', json=payload)
			response.raise_for_status()
			return response.json()

		except httpx.HTTPStatusError as e:
			self._handle_http_error(e)
			raise
		except httpx.RequestError as e:
			console.print(f'[error]Network Error:[/error] Could not reach the Control Plane at {self.base_url}')
			logger.debug(f'Request error detail: {e}')
			raise

	def sync_inventory(self, resources_data: list[dict]) -> list[dict]:
		"""
		Sends local resource inventory to the Control Plane.
		"""
		payload = {'resources': resources_data}

		try:
			response = self._client.put('/v1/resources/', json=payload)
			response.raise_for_status()
			return response.json()

		except httpx.HTTPStatusError as e:
			self._handle_http_error(e)
			raise
		except httpx.RequestError:
			console.print('[error]Network Error:[/error] Failed to sync inventory.')
			raise

	def fetch_obligations(self) -> list[dict]:
		"""
		Retrieves all active obligations for the current project.
		"""
		try:
			response = self._client.get('/v1/obligations/')
			response.raise_for_status()
			return response.json()

		except httpx.HTTPStatusError as e:
			self._handle_http_error(e)
			raise
		except httpx.RequestError:
			console.print('[error]Network Error:[/error] Failed to fetch obligations.')
			raise

	def get_audit_proof(self, log_id: str) -> dict:
		"""
		Fetches the cryptographic proof bundle for a specific log ID.
		"""
		try:
			response = self._client.get(f'/v1/audit/proof/{log_id}')
			response.raise_for_status()
			return response.json()
		except httpx.HTTPStatusError as e:
			self._handle_http_error(e)
			raise
		except httpx.RequestError:
			console.print('[error]Network Error:[/error] Failed to fetch audit proof.')
			raise

	def close(self):
		"""Cleanly close the connection pool."""
		self._client.close()

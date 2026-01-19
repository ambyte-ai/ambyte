import logging

import httpx
from ambyte_schemas.models.inventory import BatchResourceCreate, ResourceCreate

from .config import settings

logger = logging.getLogger('ambyte.connector.databricks.sink')


class AmbyteSink:
	"""
	Pushes discovered resources to the Ambyte Control Plane.
	"""

	def __init__(self):
		self.client = httpx.Client(
			base_url=str(settings.CONTROL_PLANE_URL).rstrip('/'),
			headers={
				'Authorization': f'Bearer {settings.control_plane_api_key_val}',
				'User-Agent': 'ambyte-connector-databricks/0.1.0',
				'Content-Type': 'application/json',
			},
			timeout=30.0,  # Generous timeout for batch operations
		)

	def push_batch(self, resources: list[ResourceCreate]) -> int:
		"""
		Sends a batch of resources to the inventory endpoint.
		Returns the number of successfully processed items.
		"""
		if not resources:
			return 0

		# Wrap in the specific Pydantic model expected by the API
		# The API endpoint is: PUT /v1/resources/
		payload_model = BatchResourceCreate(resources=resources)

		# Serialize to JSON-compatible dict
		payload_dict = payload_model.model_dump(mode='json')

		try:
			response = self.client.put('/v1/resources/', json=payload_dict)
			response.raise_for_status()

			# The API returns the list of upserted resources
			result_list = response.json()
			count = len(result_list)

			logger.info(f'Successfully synced batch of {count} resources to Ambyte.')
			return count

		except httpx.HTTPStatusError as e:
			# 4xx Client Errors (Config issues)
			if e.response.status_code == 401:
				logger.critical('Authentication Failed. Check AMBYTE_CONNECTOR_API_KEY.')
			elif e.response.status_code == 403:
				logger.critical("Permission Denied. Ensure API Key has 'resource:write' scope.")
			elif e.response.status_code == 422:
				logger.error(f'Validation Error: {e.response.text}')
			else:
				logger.error(f'API Error ({e.response.status_code}): {e.response.text}')

			# Re-raise to stop the sync loop (fail fast on config errors)
			raise e

		except httpx.RequestError as e:
			# Network Errors (Connectivity)
			logger.error(f'Network Error connecting to Control Plane: {e}')
			raise e

	def close(self):
		"""Clean up the connection pool."""
		self.client.close()

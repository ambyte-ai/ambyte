import logging
from pathlib import Path
from typing import Protocol

import httpx
import yaml
from ambyte_schemas.models.inventory import BatchResourceCreate, ResourceCreate
from ambyte_schemas.models.lineage import LineageEvent, Run

from ambyte_databricks.config import settings

logger = logging.getLogger('ambyte.connector.databricks.sink')


class SinkProtocol(Protocol):
	"""
	Interface definition for all Sink implementations.
	Ensures type safety when swapping between AmbyteSink, ConsoleSink, etc.
	"""

	def push_batch(self, resources: list[ResourceCreate]) -> int: ...

	def push_lineage(self, run: Run, event: LineageEvent) -> None: ...

	def close(self) -> None: ...


class AmbyteSink:
	"""
	Pushes discovered resources to the Ambyte Control Plane.
	"""

	def __init__(self):
		if not settings.control_plane_api_key_val:
			raise ValueError(
				'Missing API Key. To push lineage or inventory to the Cloud, you must set AMBYTE_DATABRICKS_API_KEY.'
			)
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

	def push_lineage(self, run: Run, event: LineageEvent) -> None:
		"""
		Sends Lineage data.
		Note: We must push the 'Run' first, as the 'Event' has a foreign key to it.
		"""
		try:
			# 1. Push Run (Upsert semantics in API)
			# We map our internal Domain Model (Run) to the API Payload.
			run_payload = {
				'external_run_id': run.id,
				'run_type': run.type.name if hasattr(run.type, 'name') else str(run.type),
				'triggered_by': run.triggered_by.id if run.triggered_by else None,
				'started_at': run.start_time.isoformat() if run.start_time else None,
				'ended_at': run.end_time.isoformat() if run.end_time else None,
				'success': run.success,
			}

			resp_run = self.client.post('/v1/lineage/run', json=run_payload)
			resp_run.raise_for_status()

			# 2. Push Event (Edges)
			event_payload = {'external_run_id': event.run_id, 'inputs': event.input_urns, 'outputs': event.output_urns}

			resp_event = self.client.post('/v1/lineage/event', json=event_payload)
			resp_event.raise_for_status()

			logger.debug(f'Pushed lineage for run {run.id}')

		except httpx.HTTPStatusError as e:
			self._handle_http_error(e)
			# We log error but don't re-raise here to allow the loop to continue
			# processing other lineage events if one is malformed.
			logger.error(f'Failed to push lineage event {event.run_id}')
		except httpx.RequestError as e:
			logger.error(f'Network Error: {e}')

	def _handle_http_error(self, e: httpx.HTTPStatusError):
		"""Standard error formatting"""
		code = e.response.status_code
		if code == 401:
			logger.critical('Authentication Failed. Check AMBYTE_DATABRICKS_API_KEY.')
		elif code == 403:
			logger.critical('Permission Denied. Ensure API Key has correct scopes (resource:write, lineage:write).')
		elif code == 422:
			logger.error(f'Validation Error: {e.response.text}')
		else:
			logger.error(f'API Error ({code}): {e.response.text}')

	def close(self):
		"""Clean up the connection pool."""
		self.client.close()


class LocalFileSink:
	"""Open Source Mode: Writes to resources.yaml for local compilation"""

	def __init__(self, output_path: str = 'resources.yaml'):
		self.output_path = Path(output_path)
		self.all_resources: list[dict] = []

	def push_batch(self, resources: list[ResourceCreate]) -> int:
		# We accumulate everything in memory for local file write
		# (Inventory lists are usually small enough for RAM)
		for r in resources:
			# Dump to JSON-compatible dict to handle Datetime/Enums
			self.all_resources.append(r.model_dump(mode='json'))
		return len(resources)

	def push_lineage(self, run: Run, event: LineageEvent) -> None:
		"""
		Local lineage isn't fully supported as a file format yet,
		but we log it for debug.
		"""
		logger.info(
			f'[Local] Lineage Captured: {run.id} | {len(event.input_urns)} inputs -> {len(event.output_urns)} outputs'
		)

	def close(self):
		"""Write the accumulated list to disk on close"""
		if not self.all_resources:
			return

		data = {'resources': self.all_resources}

		with open(self.output_path, 'w', encoding='utf-8') as f:
			yaml.dump(data, f, sort_keys=False)

		logger.info(f'Inventory written to {self.output_path.absolute()}')


class ConsoleSink:
	"""Dry Run Mode"""

	def push_batch(self, resources: list[ResourceCreate]) -> int:
		for r in resources:
			logger.info(f'[Dry Run] Found: {r.urn}')
		return len(resources)

	def push_lineage(self, run: Run, event: LineageEvent) -> None:
		inputs = ', '.join(event.input_urns) or 'None'
		outputs = ', '.join(event.output_urns) or 'None'
		user = run.triggered_by.id if run.triggered_by else 'Unknown'
		logger.info(f'[Dry Run] Lineage: [{inputs}] -> [{outputs}] by {user}')

	def close(self):
		pass

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx
from ambyte.config import get_config

if TYPE_CHECKING:
	from ambyte.core.decision import DecisionEngine

logger = logging.getLogger('ambyte.core.watcher')


class PolicyWatcher:
	"""
	Polls the Control Plane for policy version changes.
	When a change is detected, invalidates the DecisionEngine cache.
	"""

	def __init__(self, decision_engine: 'DecisionEngine'):
		self.decision_engine = decision_engine
		self.config = get_config()
		self._current_version: str | None = None
		self._running = False
		self._task: asyncio.Task | None = None

	def start(self):
		"""Start the background polling loop."""
		if self._running:
			return

		self._running = True
		try:
			loop = asyncio.get_running_loop()
			self._task = loop.create_task(self._poll_loop())
			logger.info('PolicyWatcher started (interval: %.1fs)', self.config.policy_poll_interval)
		except RuntimeError:
			# No running loop - we're in sync context, skip background polling
			logger.debug('No event loop running, PolicyWatcher will not start background polling')
			self._running = False

	def stop(self):
		"""Stop the background polling loop."""
		self._running = False
		if self._task:
			self._task.cancel()
			self._task = None
			logger.info('PolicyWatcher stopped')

	async def _poll_loop(self):
		"""Background loop that polls for policy version changes."""
		while self._running:
			try:
				await self._check_version()
			except Exception as e:
				logger.warning('PolicyWatcher poll error: %s', e)

			await asyncio.sleep(self.config.policy_poll_interval)

	async def _check_version(self):
		"""Check the policy version via HEAD request."""
		api_key = self.config.api_key_value
		if not api_key:
			return

		url = f'{self.config.control_plane_url}api/v1/projects/me/status'

		async with httpx.AsyncClient() as client:
			response = await client.head(
				url,
				headers={'Authorization': f'Bearer {api_key}'},
				timeout=5.0,
			)

			if response.status_code == 200:
				new_version = response.headers.get('X-Ambyte-Policy-Version')

				if new_version and self._current_version is not None and new_version != self._current_version:
					logger.info('Policy version changed: %s -> %s', self._current_version, new_version)
					self.decision_engine.invalidate_cache()

				self._current_version = new_version

import atexit
import logging
import queue
import threading
from typing import Any, Literal

from ambyte.client import get_client
from ambyte.config import get_config

logger = logging.getLogger('ambyte.tracking')

EventType = Literal['audit', 'lineage_run', 'lineage_event']


class TrackingManager:
	"""
	Asynchronous background worker that batches Audit Logs and Lineage Events.
	Ensures that logging IO never blocks the main execution thread.
	"""

	_instance = None

	def __init__(self):
		self.config = get_config()
		self.client = get_client()

		# Infinite size queue by default, or set maxsize to prevent memory leaks
		# in extreme failure scenarios.
		self._queue: queue.Queue[tuple[EventType, dict[str, Any]]] = queue.Queue(maxsize=10000)

		self._stop_event = threading.Event()
		self._worker_thread = threading.Thread(target=self._worker_loop, name='Ambyte-Tracker', daemon=True)

		if self.config.is_enabled and self.config.enable_background_sync:
			self._worker_thread.start()
			atexit.register(self.shutdown)

	@classmethod
	def get_instance(cls):
		if cls._instance is None:
			cls._instance = TrackingManager()
		return cls._instance

	def enqueue(self, event_type: EventType, payload: dict[str, Any]):
		"""
		Non-blocking push to the queue.
		If the queue is full (rare), we drop the event to protect the app.
		"""
		if not self.config.is_enabled:
			return

		try:
			self._queue.put_nowait((event_type, payload))
		except queue.Full:
			logger.error('Ambyte Tracking Queue is full! Dropping event to prevent blocking.')

	def shutdown(self):
		"""
		Called on application exit. Attempts to flush remaining events.
		"""
		if self._stop_event.is_set():
			return

		logger.debug('Ambyte SDK shutting down. Flushing events...')
		self._stop_event.set()

		# Wake up worker immediately if it's sleeping
		if self._worker_thread.is_alive():
			# We can't easily interrupt the sleep, but the loop checks stop_event
			# We allow up to 2 seconds for final flush
			self._worker_thread.join(timeout=2.0)

		# Perform final synchronous flush of whatever is left
		self._flush_batch()

	def _worker_loop(self):
		"""
		The background thread loop.
		"""
		while not self._stop_event.is_set():
			# Sleep for interval
			if self._stop_event.wait(timeout=self.config.batch_upload_interval_seconds):
				break
			self._flush_batch()

	def _flush_batch(self):
		"""
		Drains the queue and sends data to the API.
		"""
		if self._queue.empty():
			return

		# Prepare batches
		audit_batch = []
		lineage_batch = []

		# Drain the queue up to a reasonable limit per flush (e.g., 500 items)
		count = 0
		while not self._queue.empty() and count < 500:
			try:
				evt_type, payload = self._queue.get_nowait()
				if evt_type == 'audit':
					audit_batch.append(payload)
				elif evt_type.startswith('lineage'):
					# API might handle runs and events differently,
					# but for this logic we'll assume a generic ingest endpoint
					# or separate client calls.
					lineage_batch.append((evt_type, payload))

				self._queue.task_done()
				count += 1
			except queue.Empty:
				break

		# Send to API (Swallow errors to keep thread alive)
		if audit_batch:
			self._send_audit_batch(audit_batch)

		if lineage_batch:
			self._send_lineage_batch(lineage_batch)

	def _send_audit_batch(self, batch: list[dict]):
		try:
			# Send the entire batch in one request
			self.client._client.post('/v1/audit/', json={'logs': batch})
		except Exception as e:
			logger.warning(f'Failed to upload audit batch: {e}')

	def _send_lineage_batch(self, batch: list[tuple[str, dict]]):
		try:
			for evt_type, payload in batch:
				if evt_type == 'lineage_run':
					self.client._client.post('/v1/lineage/run', json=payload)
				elif evt_type == 'lineage_event':
					self.client._client.post('/v1/lineage/event', json=payload)
		except Exception as e:
			logger.warning(f'Failed to upload lineage batch: {e}')


# Global Accessor
def get_tracker() -> TrackingManager:
	return TrackingManager.get_instance()

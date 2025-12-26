import queue
from unittest import mock

import pytest
from ambyte.config import reset_config
from ambyte.tracking.manager import TrackingManager


@pytest.fixture
def mock_client():
	"""
	Patches get_client in the manager module.
	Yields the Mock object that get_client() will return.
	"""
	with mock.patch('ambyte.tracking.manager.get_client') as mock_get:
		yield mock_get.return_value


@pytest.fixture
def clean_manager(mock_client):  # Inject mock_client to ensure patch happens first
	"""
	Resets the Singleton and Config before/after tests.
	Disables background sync by default to allow manual flushing in tests.
	"""
	reset_config()
	TrackingManager._instance = None

	# Patch config to disable auto-start of thread for unit testing logic
	with mock.patch('ambyte.tracking.manager.get_config') as mock_cfg:
		mock_cfg.return_value.is_enabled = True
		mock_cfg.return_value.enable_background_sync = False
		mock_cfg.return_value.batch_upload_interval_seconds = 0.1

		manager = TrackingManager.get_instance()
		yield manager

		# Cleanup
		manager.shutdown()
		TrackingManager._instance = None


def test_enqueue_items(clean_manager):
	"""
	Verify items are added to the internal queue.
	"""
	clean_manager.enqueue('audit', {'id': 1})
	clean_manager.enqueue('lineage_run', {'id': 2})

	assert clean_manager._queue.qsize() == 2


def test_flush_batch_routing(clean_manager, mock_client):
	"""
	Verify _flush_batch correctly separates Audit logs from Lineage events
	and calls the appropriate client endpoints.
	"""
	# Add mixed events
	clean_manager.enqueue('audit', {'audit_id': 'A1'})
	clean_manager.enqueue('lineage_run', {'run_id': 'R1'})
	clean_manager.enqueue('lineage_event', {'evt_id': 'E1'})
	clean_manager.enqueue('audit', {'audit_id': 'A2'})

	# Manually trigger flush
	clean_manager._flush_batch()

	# 1. Verify Audit Batch
	# Expecting: client._client.post('/v1/audit', json=...) called twice
	# The mock_client fixture holds the Mock object that TrackingManager.client holds.
	assert mock_client._client.post.call_count >= 3

	# We can inspect specific calls
	calls = mock_client._client.post.call_args_list

	# Extract audit calls
	audit_calls = [c for c in calls if c[0][0] == '/v1/audit']
	assert len(audit_calls) == 1
	assert audit_calls[0].kwargs['json'] == {'logs': [{'audit_id': 'A1'}, {'audit_id': 'A2'}]}

	# Extract lineage calls
	run_calls = [c for c in calls if c[0][0] == '/v1/lineage/run']
	event_calls = [c for c in calls if c[0][0] == '/v1/lineage/event']

	assert len(run_calls) == 1
	assert run_calls[0].kwargs['json'] == {'run_id': 'R1'}

	assert len(event_calls) == 1
	assert event_calls[0].kwargs['json'] == {'evt_id': 'E1'}


def test_queue_full_drops_event(clean_manager):
	"""
	Verify that if the queue is full, it drops the event rather than blocking/crashing.
	"""
	# artificially shrink queue for test
	clean_manager._queue = queue.Queue(maxsize=1)

	clean_manager.enqueue('audit', {'id': 1})

	# This should trigger queue.Full internally and log an error, but NOT raise
	clean_manager.enqueue('audit', {'id': 2})

	assert clean_manager._queue.qsize() == 1
	# Check that item 1 is still there
	assert clean_manager._queue.get()[1]['id'] == 1


def test_shutdown_flushes_remaining(mock_client):
	"""
	Verify that calling shutdown() flushes whatever is left in the queue.
	"""
	reset_config()
	TrackingManager._instance = None

	# We need a manager that THINKS it has background sync (to init thread logic)
	# but we will manually control shutdown.
	with mock.patch('ambyte.tracking.manager.get_config') as mock_cfg:
		mock_cfg.return_value.is_enabled = True
		mock_cfg.return_value.enable_background_sync = True
		# Long interval so the thread doesn't steal our item before shutdown
		mock_cfg.return_value.batch_upload_interval_seconds = 10.0

		# We manually patch get_client here because we aren't using the clean_manager fixture
		with mock.patch('ambyte.tracking.manager.get_client', return_value=mock_client):
			manager = TrackingManager.get_instance()

			# Enqueue item
			manager.enqueue('audit', {'msg': 'last_breath'})

			# Shutdown
			manager.shutdown()

			# Verify it was sent
			mock_client._client.post.assert_called_with('/v1/audit', json={'logs': [{'msg': 'last_breath'}]})

			# Verify thread is dead
			assert not manager._worker_thread.is_alive()

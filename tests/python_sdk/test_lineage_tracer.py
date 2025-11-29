from unittest import mock

import pytest
from ambyte.config import reset_config
from ambyte.context import get_current_run_id
from ambyte.tracking.lineage import trace


@pytest.fixture
def mock_tracker():
	"""
	Mock the singleton TrackingManager to capture enqueue calls
	without actually running the background worker.
	"""
	with mock.patch('ambyte.tracking.lineage.get_tracker') as mock_get:
		yield mock_get.return_value


@pytest.fixture(autouse=True)
def clean_context():
	reset_config()
	yield


def test_trace_lifecycle_success(mock_tracker):
	"""
	Verify successful run emits START and END events with success=True.
	"""
	inputs = ['urn:in:1']
	outputs = ['urn:out:1']

	with trace(name='etl_job', inputs=inputs, outputs=outputs):
		# 1. Verify Run ID is set in context
		run_id = get_current_run_id()
		assert run_id is not None

		# 2. Verify Start Event was emitted immediately
		assert mock_tracker.enqueue.call_count == 1
		start_call = mock_tracker.enqueue.call_args_list[0]
		assert start_call[0][0] == 'lineage_run'
		assert start_call[0][1]['id'] == run_id
		assert 'start_time' in start_call[0][1]

	# 3. Verify End Event and Edge Event were emitted on exit
	assert mock_tracker.enqueue.call_count == 3

	# End Run Event
	end_call = mock_tracker.enqueue.call_args_list[1]
	assert end_call[0][0] == 'lineage_run'
	assert end_call[0][1]['success'] is True
	assert 'end_time' in end_call[0][1]

	# Edge Event
	edge_call = mock_tracker.enqueue.call_args_list[2]
	assert edge_call[0][0] == 'lineage_event'
	assert edge_call[0][1]['input_urns'] == inputs
	assert edge_call[0][1]['output_urns'] == outputs


def test_trace_lifecycle_failure(mock_tracker):
	"""
	Verify exception raises propagate and emit success=False.
	"""
	with pytest.raises(ValueError):
		with trace(name='failing_job'):
			raise ValueError('Boom')

	# Verify End Event captured failure
	end_call = mock_tracker.enqueue.call_args_list[1]
	payload = end_call[0][1]

	assert payload['success'] is False


def test_trace_no_io_skip_edge(mock_tracker):
	"""
	If no inputs/outputs are provided, only Run events (Start/End) should be emitted,
	no 'lineage_event' (Edge).
	"""
	with trace(name='compute_only'):
		pass

	assert mock_tracker.enqueue.call_count == 2

	# Check types of calls
	call_types = [c[0][0] for c in mock_tracker.enqueue.call_args_list]
	assert 'lineage_event' not in call_types
	assert call_types == ['lineage_run', 'lineage_run']


def test_nested_traces(mock_tracker):
	"""
	Verify nested traces generate distinct Run IDs and the context restores correctly.
	"""
	with trace(name='outer') as outer_ctx:
		outer_id = get_current_run_id()
		assert outer_id == outer_ctx.run_id

		with trace(name='inner') as inner_ctx:
			inner_id = get_current_run_id()
			assert inner_id == inner_ctx.run_id
			assert inner_id != outer_id

		# Back in outer
		assert get_current_run_id() == outer_id

import asyncio
from unittest import mock

import pytest
from ambyte.context import (
	context,
	get_current_actor,
	get_current_run_id,
	get_extra_context,
)
from ambyte_schemas.models.common import Actor, ActorType


@pytest.fixture
def sample_actor():
	return Actor(id='user_123', type=ActorType.HUMAN, roles=['admin'])


def test_context_lifecycle(sample_actor):
	"""
	Verify that context is set upon entering the block and reset upon exiting.
	"""
	# Pre-condition: Context should be empty
	assert get_current_actor() is None
	assert get_current_run_id() is None

	with context(actor=sample_actor, run_id='run_abc'):
		# Inside: Context is set
		current = get_current_actor()
		assert current is not None
		assert current.id == 'user_123'
		assert get_current_run_id() == 'run_abc'

	# Post-condition: Context is reset
	assert get_current_actor() is None
	assert get_current_run_id() is None


def test_auto_generate_run_id():
	"""
	Verify that if no Run ID is provided, entering a context generates one.
	"""
	with context():
		run_id = get_current_run_id()
		assert run_id is not None
		assert len(run_id) > 0  # Should be a UUID string


def test_nested_contexts(sample_actor):
	"""
	Verify that nested contexts override the outer scope, and restore it on exit.
	"""
	actor2 = Actor(id='service_999', type=ActorType.SERVICE_ACCOUNT)

	with context(actor=sample_actor, run_id='outer_run'):
		assert get_current_actor().id == 'user_123'
		assert get_current_run_id() == 'outer_run'

		# Enter inner scope
		with context(actor=actor2, run_id='inner_run'):
			assert get_current_actor().id == 'service_999'
			assert get_current_run_id() == 'inner_run'

		# Exit inner scope, should return to outer state
		assert get_current_actor().id == 'user_123'
		assert get_current_run_id() == 'outer_run'


def test_extra_context_merging():
	"""
	Verify handling of the extra context dictionary.
	Note: Current implementation *replaces* the dict in a new context,
	it does not recursively merge. This test confirms that behavior.
	"""
	with context(metadata='v1'):
		assert get_extra_context() == {'metadata': 'v1'}

		# Nested replacement
		with context(region='us'):
			# It replaces, not merges, based on implementation `_extra_context.set(self.extras)`
			# If we wanted merging, the implementation would need to fetch, copy, update, set.
			assert get_extra_context() == {'region': 'us'}

		# Restore
		assert get_extra_context() == {'metadata': 'v1'}


@pytest.mark.asyncio
async def test_async_propagation(sample_actor):
	"""
	Verify that ContextVars propagate correctly into async tasks.
	"""

	async def worker():
		# This runs in a separate Task
		await asyncio.sleep(0.01)
		return get_current_actor()

	with context(actor=sample_actor):
		# Current thread has context
		assert get_current_actor().id == 'user_123'

		# Spawn a task. Python's asyncio context propagation should handle this.
		result_actor = await asyncio.create_task(worker())

		assert result_actor is not None
		assert result_actor.id == 'user_123'


def test_otel_integration(sample_actor):
	"""
	Verify that if OpenTelemetry is present, we try to set span attributes.
	"""
	# Mock the trace module entirely to avoid needing a real OTel setup
	with mock.patch('ambyte.context.trace') as mock_trace:
		# Setup mock span
		mock_span = mock.Mock()
		mock_trace.get_current_span.return_value = mock_span

		# Mock availability
		with mock.patch('ambyte.context._OTEL_AVAILABLE', True):
			with context(actor=sample_actor, run_id='otel_run'):
				pass

			# Verify calls
			mock_span.set_attribute.assert_any_call('ambyte.run_id', 'otel_run')
			mock_span.set_attribute.assert_any_call('ambyte.actor.id', 'user_123')

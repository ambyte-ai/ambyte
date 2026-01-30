import os
from unittest import mock

import pytest
from ambyte.config import reset_config
from ambyte.core.decision import DecisionEngine


@pytest.fixture(autouse=True)
def clean_state():
	"""Reset singleton state before each test."""
	reset_config()
	DecisionEngine._instance = None
	yield
	DecisionEngine._instance = None
	reset_config()


class TestPolicyWatcher:
	"""Tests for the PolicyWatcher class."""

	def test_watcher_initialized_in_remote_mode(self):
		"""Verify PolicyWatcher is created when mode is REMOTE."""
		with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'REMOTE'}):
			engine = DecisionEngine.get_instance()
			assert engine._watcher is not None

	def test_watcher_not_initialized_in_local_mode(self, tmp_path):
		"""Verify PolicyWatcher is NOT created when mode is LOCAL."""
		# Create a minimal policy file
		policy_file = tmp_path / 'policy.json'
		policy_file.write_text('{"metadata": {"compiler_version": "test"}, "policies": {}, "schema_version": "1.0.0"}')

		env_vars = {'AMBYTE_MODE': 'LOCAL', 'AMBYTE_LOCAL_POLICY_PATH': str(policy_file)}
		with mock.patch.dict(os.environ, env_vars):
			engine = DecisionEngine.get_instance()
			assert engine._watcher is None

	def test_watcher_not_initialized_in_off_mode(self):
		"""Verify PolicyWatcher is NOT created when mode is OFF."""
		with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'OFF'}):
			engine = DecisionEngine.get_instance()
			assert engine._watcher is None

	@pytest.mark.asyncio
	async def test_watcher_detects_version_change(self):
		"""Verify PolicyWatcher calls invalidate_cache when version changes."""
		from ambyte.core.watcher import PolicyWatcher

		# Create mock decision engine
		mock_engine = mock.MagicMock()
		mock_engine.invalidate_cache = mock.MagicMock()

		with mock.patch.dict(os.environ, {'AMBYTE_API_KEY': 'test_key'}):
			watcher = PolicyWatcher(mock_engine)
			watcher._current_version = 'old-version-uuid'

			# Mock the HTTP response
			mock_response = mock.MagicMock()
			mock_response.status_code = 200
			mock_response.headers = {'X-Ambyte-Policy-Version': 'new-version-uuid'}

			with mock.patch('httpx.AsyncClient') as mock_client_class:
				mock_client = mock.AsyncMock()
				mock_client.head = mock.AsyncMock(return_value=mock_response)
				mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
				mock_client.__aexit__ = mock.AsyncMock(return_value=None)
				mock_client_class.return_value = mock_client

				await watcher._check_version()

				# Verify cache was invalidated
				mock_engine.invalidate_cache.assert_called_once()
				assert watcher._current_version == 'new-version-uuid'

	@pytest.mark.asyncio
	async def test_watcher_no_invalidation_on_same_version(self):
		"""Verify PolicyWatcher does NOT invalidate cache when version is unchanged."""
		from ambyte.core.watcher import PolicyWatcher

		mock_engine = mock.MagicMock()
		mock_engine.invalidate_cache = mock.MagicMock()

		with mock.patch.dict(os.environ, {'AMBYTE_API_KEY': 'test_key'}):
			watcher = PolicyWatcher(mock_engine)
			watcher._current_version = 'same-version-uuid'

			mock_response = mock.MagicMock()
			mock_response.status_code = 200
			mock_response.headers = {'X-Ambyte-Policy-Version': 'same-version-uuid'}

			with mock.patch('httpx.AsyncClient') as mock_client_class:
				mock_client = mock.AsyncMock()
				mock_client.head = mock.AsyncMock(return_value=mock_response)
				mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
				mock_client.__aexit__ = mock.AsyncMock(return_value=None)
				mock_client_class.return_value = mock_client

				await watcher._check_version()

				# Verify cache was NOT invalidated
				mock_engine.invalidate_cache.assert_not_called()

	@pytest.mark.asyncio
	async def test_watcher_first_check_no_invalidation(self):
		"""Verify first version check does not invalidate (no previous version)."""
		from ambyte.core.watcher import PolicyWatcher

		mock_engine = mock.MagicMock()
		mock_engine.invalidate_cache = mock.MagicMock()

		with mock.patch.dict(os.environ, {'AMBYTE_API_KEY': 'test_key'}):
			watcher = PolicyWatcher(mock_engine)
			assert watcher._current_version is None

			mock_response = mock.MagicMock()
			mock_response.status_code = 200
			mock_response.headers = {'X-Ambyte-Policy-Version': 'first-version'}

			with mock.patch('httpx.AsyncClient') as mock_client_class:
				mock_client = mock.AsyncMock()
				mock_client.head = mock.AsyncMock(return_value=mock_response)
				mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
				mock_client.__aexit__ = mock.AsyncMock(return_value=None)
				mock_client_class.return_value = mock_client

				await watcher._check_version()

				# No invalidation on first check
				mock_engine.invalidate_cache.assert_not_called()
				assert watcher._current_version == 'first-version'

	def test_watcher_start_stop(self):
		"""Verify watcher can be started and stopped."""
		from ambyte.core.watcher import PolicyWatcher

		mock_engine = mock.MagicMock()
		watcher = PolicyWatcher(mock_engine)

		# Without event loop, start should be a no-op
		watcher.start()
		assert watcher._running is False  # No event loop

		watcher.stop()
		assert watcher._running is False


class TestDecisionEngineInvalidateCache:
	"""Tests for DecisionEngine.invalidate_cache method."""

	def test_invalidate_cache_clears_cache(self):
		"""Verify invalidate_cache clears all cached decisions."""
		with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'OFF'}):
			engine = DecisionEngine.get_instance()

			# Populate cache
			engine._cache['key1'] = True
			engine._cache['key2'] = False
			assert len(engine._cache) == 2

			# Invalidate
			engine.invalidate_cache()

			assert len(engine._cache) == 0

	def test_invalidate_cache_allows_fresh_decisions(self):
		"""Verify that after invalidation, new decisions are fetched."""
		engine = DecisionEngine.get_instance()

		with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
			mock_client = mock_get_client.return_value
			mock_client.check_permission.return_value = True

			# First call - hits network
			engine.check_access('urn:test', 'read')
			assert mock_client.check_permission.call_count == 1

			# Second call - cache hit
			engine.check_access('urn:test', 'read')
			assert mock_client.check_permission.call_count == 1

			# Invalidate cache
			engine.invalidate_cache()

			# Third call - hits network again
			engine.check_access('urn:test', 'read')
			assert mock_client.check_permission.call_count == 2

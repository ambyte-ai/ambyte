import os
from unittest import mock

import pytest
from ambyte.config import reset_config
from ambyte.context import context as ambyte_context_manager
from ambyte.core.decision import DecisionEngine
from ambyte_rules.models import ConflictTrace, EffectiveGeofencing, ResolvedPolicy
from ambyte_schemas.models.artifact import BuildMetadata, PolicyBundle
from ambyte_schemas.models.common import Actor, ActorType


@pytest.fixture(autouse=True)
def clean_engine():
	"""
	Reset the singleton state before every test to ensure isolation.
	"""
	reset_config()
	DecisionEngine._instance = None
	yield
	DecisionEngine._instance = None
	reset_config()


def test_off_mode_short_circuit():
	"""
	Verify that AMBYTE_MODE=OFF returns True immediately without hitting the client.
	"""
	with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'OFF'}):
		engine = DecisionEngine.get_instance()

		# Mock the client to ensure it's NEVER called
		with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
			allowed = engine.check_access('urn:test', 'read')

			assert allowed is True
			mock_get_client.assert_not_called()


def test_remote_mode_delegation():
	"""
	Verify that REMOTE mode delegates execution to the AmbyteClient.
	"""
	with mock.patch.dict(os.environ, {'AMBYTE_MODE': 'REMOTE'}):
		engine = DecisionEngine.get_instance()

		with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
			mock_client = mock_get_client.return_value
			mock_client.check_permission.return_value = True

			result = engine.check_access('urn:remote', 'write')

			assert result is True
			mock_client.check_permission.assert_called_once_with(
				resource_urn='urn:remote',
				action='write',
				actor_id='anonymous',  # Default if no context
				context={},
			)


def test_caching_logic():
	"""
	Verify that repeated calls with identical context hit the cache
	instead of the network.
	"""
	engine = DecisionEngine.get_instance()

	with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
		mock_client = mock_get_client.return_value
		mock_client.check_permission.return_value = True

		# Call 1: Network Hit
		engine.check_access('urn:cache', 'read', context={'a': 1})

		# Call 2: Cache Hit
		engine.check_access('urn:cache', 'read', context={'a': 1})

		# Verify network called only once
		assert mock_client.check_permission.call_count == 1

		# Call 3: Different Context -> Network Hit
		engine.check_access('urn:cache', 'read', context={'a': 2})
		assert mock_client.check_permission.call_count == 2


def test_context_resolution_affects_cache_key():
	"""
	Verify that implicit ContextVars (Actor, RunID) change the cache key.
	"""
	engine = DecisionEngine.get_instance()
	actor_a = Actor(id='user_a', type=ActorType.HUMAN)
	actor_b = Actor(id='user_b', type=ActorType.HUMAN)

	with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
		mock_client = mock_get_client.return_value
		mock_client.check_permission.return_value = True

		# 1. User A checks access
		with ambyte_context_manager(actor=actor_a):
			engine.check_access('urn:data', 'read')

		# 2. User B checks access (Same resource/action)
		with ambyte_context_manager(actor=actor_b):
			engine.check_access('urn:data', 'read')

		# Should be 2 distinct calls because the actor ID is different
		assert mock_client.check_permission.call_count == 2

		# Verify args passed to client
		call_args_list = mock_client.check_permission.call_args_list
		assert call_args_list[0].kwargs['actor_id'] == 'user_a'
		assert call_args_list[1].kwargs['actor_id'] == 'user_b'


def test_local_mode_file_loading(tmp_path):
	"""
	Verify that LOCAL mode loads policies from a JSON file and bypasses the network.
	"""

	# 1. Construct Valid Policy Objects
	# Policy A: Allowed (No constraints)
	policy_allow = ResolvedPolicy(resource_urn='urn:local:allowed')

	# Policy B: Denied (Global Geofencing Ban)
	trace = ConflictTrace(winning_obligation_id='obl-1', winning_source_id='TEST', description='Blocked for testing')
	policy_deny = ResolvedPolicy(
		resource_urn='urn:local:denied', geofencing=EffectiveGeofencing(is_global_ban=True, reason=trace)
	)

	# 2. Wrap in Bundle
	bundle = PolicyBundle(
		metadata=BuildMetadata(compiler_version='test'),
		policies={'urn:local:allowed': policy_allow, 'urn:local:denied': policy_deny},
		schema_version='1.0.0',
	)

	# 3. Write JSON to disk
	policy_file = tmp_path / 'policy.json'
	with open(policy_file, 'w', encoding='utf-8') as f:
		f.write(bundle.model_dump_json())

	# 4. Configure SDK to use it
	env_vars = {'AMBYTE_MODE': 'LOCAL', 'AMBYTE_LOCAL_POLICY_PATH': str(policy_file)}

	with mock.patch.dict(os.environ, env_vars):
		engine = DecisionEngine.get_instance()

		# Verify allow logic
		assert engine.check_access('urn:local:allowed', 'read') is True

		# Verify deny logic
		assert engine.check_access('urn:local:denied', 'read', context={'region': 'US'}) is False

		# Verify default deny (unknown resource)
		assert engine.check_access('urn:unknown', 'read') is False


@pytest.mark.asyncio
async def test_async_check_access():
	"""
	Verify the async entry point delegates to the async client method.
	"""
	engine = DecisionEngine.get_instance()

	with mock.patch('ambyte.core.decision.get_client') as mock_get_client:
		mock_client = mock_get_client.return_value
		# Mock the async method
		mock_client.check_permission_async = mock.AsyncMock(return_value=True)

		result = await engine.check_access_async('urn:async', 'read')

		assert result is True
		mock_client.check_permission_async.assert_awaited_once()

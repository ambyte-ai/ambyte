import logging
from pathlib import Path
from typing import Any, Optional

from ambyte.client import get_client
from ambyte.config import AmbyteMode, get_config
from ambyte.context import get_current_actor, get_current_run_id, get_extra_context
from ambyte.core.evaluator import LocalPolicyEvaluator
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.artifact import PolicyBundle
from cachetools import TTLCache
from pydantic import ValidationError

logger = logging.getLogger('ambyte.core.decision')


class DecisionEngine:
	"""
	The Policy Decision Point (PDP).

	Responsible for:
	1. Resolving the full context of a request (Actor + Run ID + Attributes).
	2. Checking the decision cache to avoid redundant calculations/calls.
	3. Routing the check to the correct backend (Remote API vs Local Evaluator).
	"""

	_instance: Optional['DecisionEngine'] = None

	def __init__(self):
		self.config = get_config()

		# Initialize Cache
		# Keys are hashes of (urn, action, actor_id, frozen_context)
		# Values are booleans (True=Allow, False=Deny)
		# TODO: push "Invalidate" signals (via Redis/Websockets) to the SDK so policy changes take effect instantly
		# rather than waiting for the TTL to expire.
		self._cache = TTLCache(maxsize=10000, ttl=self.config.decision_cache_ttl_seconds)

		# Local Policy State (for LOCAL mode)
		self._local_policies: dict[str, ResolvedPolicy] = {}
		self.evaluator = LocalPolicyEvaluator()

		if self.config.mode == AmbyteMode.LOCAL:
			self._load_local_policy()

	@classmethod
	def get_instance(cls) -> 'DecisionEngine':
		if cls._instance is None:
			cls._instance = DecisionEngine()
		return cls._instance

	# ==========================================================================
	# PUBLIC API
	# ==========================================================================

	def check_access(self, resource_urn: str, action: str, context: dict[str, Any] | None = None) -> bool:
		"""
		Synchronous entry point for permission checking.
		"""
		# 0. Short-circuit if OFF
		if self.config.mode == AmbyteMode.OFF:
			return True

		# 1. Resolve Context & Actor
		actor_id, final_context = self._resolve_full_context(context)

		# 2. Check Cache
		cache_key = self._make_cache_key(resource_urn, action, actor_id, final_context)
		if cache_key in self._cache:
			return self._cache[cache_key]

		# 3. Execute Strategy
		is_allowed = False
		if self.config.mode == AmbyteMode.REMOTE:
			is_allowed = self._execute_remote(resource_urn, action, actor_id, final_context)
		elif self.config.mode == AmbyteMode.LOCAL:
			is_allowed = self._execute_local(resource_urn, action, final_context)

		# 4. Update Cache & Return
		self._cache[cache_key] = is_allowed
		return is_allowed

	async def check_access_async(self, resource_urn: str, action: str, context: dict[str, Any] | None = None) -> bool:
		"""
		Asynchronous entry point for permission checking.
		"""
		if self.config.mode == AmbyteMode.OFF:
			return True

		actor_id, final_context = self._resolve_full_context(context)

		cache_key = self._make_cache_key(resource_urn, action, actor_id, final_context)
		if cache_key in self._cache:
			return self._cache[cache_key]

		is_allowed = False
		if self.config.mode == AmbyteMode.REMOTE:
			# Use the Async Client
			is_allowed = await get_client().check_permission_async(resource_urn, action, actor_id, final_context)
		elif self.config.mode == AmbyteMode.LOCAL:
			# Local is always sync (memory lookup), just wrap it
			is_allowed = self._execute_local(resource_urn, action, final_context)

		self._cache[cache_key] = is_allowed
		return is_allowed

	# ==========================================================================
	# INTERNAL LOGIC
	# ==========================================================================

	def _resolve_full_context(self, explicit_context: dict | None) -> tuple[str, dict]:
		"""
		Merges explicitly passed arguments with implicit ContextVars.
		Returns (actor_id, merged_context_dict).
		"""
		# 1. Actor
		actor = get_current_actor()
		actor_id = actor.id if actor else 'anonymous'

		# 2. Context
		# Start with extras from ContextVars
		final_context = get_extra_context().copy()

		# Merge explicit args
		if explicit_context:
			final_context.update(explicit_context)

		# Inject Run ID
		run_id = get_current_run_id()
		if run_id:
			final_context['run_id'] = run_id

		return actor_id, final_context

	def _make_cache_key(self, urn: str, action: str, actor_id: str, context: dict) -> tuple:
		"""
		Creates a hashable key for the dictionary cache.
		Dictionaries are mutable, so we freeze them into sorted tuples.
		"""
		# Convert context dict to a sorted tuple of items for hashing
		# We stringify values to ensure they are hashable (avoid nested dict issues for now)
		ctx_hash = tuple(sorted((k, str(v)) for k, v in context.items()))
		return (urn, action, actor_id, ctx_hash)

	def _execute_remote(self, urn: str, action: str, actor_id: str, context: dict) -> bool:
		"""Delegates to the HTTP Client."""
		return get_client().check_permission(resource_urn=urn, action=action, actor_id=actor_id, context=context)

	def _execute_local(self, urn: str, action: str, context: dict) -> bool:
		"""
		Evaluates the request against the loaded PolicyBundle.
		"""
		# 1. Lookup Policy
		policy = self._local_policies.get(urn)

		if not policy:
			# Default Deny if no policy exists for this specific resource
			logger.debug("No local policy found for '%s'. Defaulting to DENY.", urn)
			return False

		# 2. Evaluate
		allowed, reason = self.evaluator.evaluate(policy, action, context)

		if not allowed:
			logger.info("Local Access Denied for '%s': %s", urn, reason)

		return allowed

	def _load_local_policy(self):
		"""
		Loads the 'local_policies.json' artifact into Pydantic models.
		"""
		path_str = self.config.local_policy_path
		if not path_str:
			logger.warning("Ambyte running in LOCAL mode but 'local_policy_path' is not set. Defaulting to DENY ALL.")
			return

		path = Path(path_str)
		if not path.exists():
			logger.error('Local policy file not found at: %s. Defaulting to DENY ALL.', path)
			return

		try:
			with open(path, encoding='utf-8') as f:
				json_content = f.read()

			# Parse using Pydantic Schema
			bundle = PolicyBundle.model_validate_json(json_content)

			# Store map for O(1) lookup
			self._local_policies = bundle.policies

			logger.info(
				'Loaded policy bundle v%s (%d policies) from %s', bundle.schema_version, len(self._local_policies), path
			)

		except ValidationError as e:
			logger.error('Invalid policy bundle schema: %s', e)
		except Exception as e:
			logger.error('Failed to load local policy file: %s', e)


# Global Accessor
def get_decision_engine() -> DecisionEngine:
	return DecisionEngine.get_instance()

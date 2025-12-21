import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

# Import Logic Libraries (Shared Code)
from ambyte_compiler.matcher import ResourceMatcher
from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import (
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePurpose,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import Obligation as PydanticObligation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import App Components
from src.core.cache import cache
from src.db.models.inventory import Resource
from src.db.models.policy import Obligation as ObligationModel
from src.schemas.check import CheckRequest, CheckResponse

logger = logging.getLogger(__name__)


class ServerPolicyEvaluator:
	"""
	Evaluates a specific Action/Context against a ResolvedPolicy.
	Mirrors the logic in the Python SDK's LocalPolicyEvaluator.
	"""

	def evaluate(self, policy: ResolvedPolicy, action: str, context: dict[str, Any]) -> tuple[bool, str]:
		# 1. Geofencing
		if policy.geofencing:
			allowed, reason = self._check_geo(policy.geofencing, context)
			if not allowed:
				return False, reason

		# 2. Purpose
		if policy.purpose:
			allowed, reason = self._check_purpose(policy.purpose, context)
			if not allowed:
				return False, reason

		# 3. AI Rules
		if policy.ai_rules:
			allowed, reason = self._check_ai(policy.ai_rules, action)
			if not allowed:
				return False, reason

		# 4. Retention
		if policy.retention:
			allowed, reason = self._check_retention(policy.retention, context)
			if not allowed:
				return False, reason

		return True, 'Access Allowed'

	def _get_ctx(self, ctx: dict, keys: list[str]) -> Any | None:
		"""Case-insensitive key lookup."""
		normalized = {k.lower(): v for k, v in ctx.items()}
		for k in keys:
			if k in ctx:
				return ctx[k]
			if k.lower() in normalized:
				return normalized[k.lower()]
		return None

	def _check_geo(self, rule: EffectiveGeofencing, context: dict) -> tuple[bool, str]:
		if rule.is_global_ban:
			return False, 'Global Data Ban Active'

		region = str(self._get_ctx(context, ['region', 'geo', 'location', 'country']) or '').upper()

		if not region:
			if rule.allowed_regions or rule.blocked_regions:
				return False, "Missing 'region' in context required for Geofencing."
			return True, 'Pass'

		if region in rule.blocked_regions:
			return False, f"Region '{region}' is explicitly blocked."

		if rule.allowed_regions and region not in rule.allowed_regions:
			return False, f"Region '{region}' is not in allowed list."

		return True, 'Pass'

	def _check_purpose(self, rule: EffectivePurpose, context: dict) -> tuple[bool, str]:
		purpose = str(self._get_ctx(context, ['purpose', 'usage', 'intent']) or '').upper()

		if not purpose:
			if rule.allowed_purposes or rule.denied_purposes:
				return False, "Missing 'purpose' in context."
			return True, 'Pass'

		if purpose in rule.denied_purposes:
			return False, f"Purpose '{purpose}' is forbidden."

		if rule.allowed_purposes and purpose not in rule.allowed_purposes:
			return False, f"Purpose '{purpose}' is not explicitly allowed."

		return True, 'Pass'

	def _check_ai(self, rule: EffectiveAiRules, action: str) -> tuple[bool, str]:
		act = action.lower()
		if 'train' in act and not rule.training_allowed:
			return False, 'AI Training prohibited.'
		if ('fine' in act and 'tune' in act) and not rule.fine_tuning_allowed:
			return False, 'Fine-tuning prohibited.'
		if ('rag' in act or 'retrieval' in act) and not rule.rag_allowed:
			return False, 'RAG usage prohibited.'
		return True, 'Pass'

	def _check_retention(self, rule: EffectiveRetention, context: dict) -> tuple[bool, str]:
		if rule.is_indefinite:
			return True, 'Legal Hold Active'

		created_val = self._get_ctx(context, ['created_at', 'date'])
		if not created_val:
			# Server-side default: Fail Open with Warning (or Configurable)
			return True, 'Missing creation date for retention check.'

		try:
			if isinstance(created_val, str):
				created_at = datetime.fromisoformat(created_val)
			else:
				created_at = created_val

			if created_at.tzinfo is None:
				created_at = created_at.replace(tzinfo=timezone.utc)

			age = datetime.now(timezone.utc) - created_at
			if age > rule.duration:
				return False, f'Data expired. Age {age.days}d > Limit {rule.duration.days}d.'
		except Exception:
			return True, 'Invalid date format.'

		return True, 'Pass'


class DecisionService:
	"""
	Orchestrator for the Hot Path.
	"""

	_evaluator = ServerPolicyEvaluator()
	_matcher = ResourceMatcher()
	_resolver = ConflictResolutionEngine()

	@classmethod
	async def evaluate_access(cls, db: AsyncSession, project_id: UUID, req: CheckRequest) -> CheckResponse:
		"""
		Main Entrypoint.
		1. Resolve Policy (Cache -> Compute)
		2. Evaluate Specific Request
		"""
		# 1. Resolve Effective Policy (The mathematical truth)
		resolved_policy, cache_hit = await cls._resolve_effective_policy(db, project_id, req.resource_urn)

		# 2. Evaluate specific context against policy
		allowed, reason = cls._evaluator.evaluate(resolved_policy, req.action, req.context)

		return CheckResponse(
			allowed=allowed,
			reason=reason,
			cache_hit=cache_hit,
			# In a real app, trace_id would generate an audit log reference # TODO
			trace_id=None,
			# Include policy details for debugging if needed, usually omitted in prod for bandwidth
			policy_snapshot=None,
		)

	@classmethod
	async def _resolve_effective_policy(
		cls, db: AsyncSession, project_id: UUID, urn: str
	) -> tuple[ResolvedPolicy, bool]:
		"""
		Fetches the 'ResolvedPolicy' object.
		Strategically uses Redis to avoid re-computing complex rules.
		"""
		cache_key = f'decision:{project_id}:{urn}'

		# --- A. CACHE HIT ---
		cached = await cache.get_model(cache_key, ResolvedPolicy)
		if cached:
			return cached, True

		# --- B. CACHE MISS (COMPUTE) ---

		# 1. Fetch Inventory Context (Tags)
		# We need to know what 'tags' this resource has to match against policies.
		res_query = select(Resource).where(Resource.project_id == project_id, Resource.urn == urn)
		res_result = await db.execute(res_query)
		resource_obj = res_result.scalars().first()

		resource_tags = {}
		if resource_obj and resource_obj.attributes:
			resource_tags = resource_obj.attributes.get('tags', {})

		# 2. Fetch All Obligations for Project
		# NOTE: For MVP (<10k policies), fetching all is faster than complex DB filtering.
		# Future: Use Postgres JSONB indexing to filter `target` column in SQL. TODO
		obl_query = select(ObligationModel).where(
			ObligationModel.project_id == project_id, ObligationModel.is_active == True
		)
		obl_result = await db.execute(obl_query)
		raw_obligations = obl_result.scalars().all()

		# 3. Match & Resolve
		# Convert DB Models -> Pydantic Schemas for the Engine
		pydantic_obs = [PydanticObligation(**ob.definition) for ob in raw_obligations]

		# Filter: Which policies apply to THIS specific URN + Tags?
		matched_obs = [ob for ob in pydantic_obs if cls._matcher.matches(urn, resource_tags, ob)]

		# Resolve: Reduce conflicts to single truth
		resolved_policy = cls._resolver.resolve(urn, matched_obs)

		# 4. Cache Result (TTL: 5 Minutes)
		# We use a short TTL so policy changes propagate reasonably fast
		# even without explicit invalidation logic (safety net).
		await cache.set_model(cache_key, resolved_policy, ttl_seconds=300)

		return resolved_policy, False

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

# Import Logic Libraries (Shared Code)
from ambyte_compiler.matcher import ResourceMatcher
from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.lineage import LineageGraph
from ambyte_rules.models import (
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePurpose,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import Obligation as PydanticObligation
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import App Components
from src.core.cache import cache
from src.db.models.inventory import Resource
from src.db.models.policy import Obligation as ObligationModel
from src.schemas.check import CheckRequest, CheckResponse
from src.services.lineage_graph_adapter import PostgresMetadataProvider

logger = logging.getLogger(__name__)


class LineageState(BaseModel):
	inherited_risk: int
	inherited_sensitivity: int
	poisoned_constraints: list[str]


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
		2. Resolve Lineage Context (Cache -> DB Graph Traversal)
		3. Evaluate Specific Request
		"""
		# 1. Resolve Effective Policy (The mathematical truth)
		resolved_policy, cache_hit_policy = await cls._resolve_effective_policy(db, project_id, req.resource_urn)

		# 2. Resolve Lineage State (The upstream truth)
		lineage_state, cache_hit_lineage = await cls._resolve_lineage_state(db, req.resource_urn)

		# 3. Inject Lineage findings into Context
		# This allows Policy Rules to act on upstream properties (e.g. "If upstream is HIGH risk, Deny")
		# We assume the policy evaluator looks for these keys if configured.
		runtime_context = req.context.copy()
		runtime_context['inherited_risk'] = lineage_state.inherited_risk
		runtime_context['inherited_sensitivity'] = lineage_state.inherited_sensitivity

		# Hard Block: Poison Pills (Upstream explicitly forbade downstream usage)
		# e.g., Data A (No AI) -> Model B. Request to Train on Model B.
		if lineage_state.poisoned_constraints and 'train' in req.action.lower():
			return CheckResponse(
				allowed=False,
				reason=f'Blocked by upstream constraint propagation. Sources: {lineage_state.poisoned_constraints}',
				cache_hit=cache_hit_lineage,
				policy_snapshot=resolved_policy,
			)

		# 4. Evaluate specific context against policy
		allowed, reason = cls._evaluator.evaluate(resolved_policy, req.action, runtime_context)

		return CheckResponse(
			allowed=allowed,
			reason=reason,
			cache_hit=cache_hit_policy and cache_hit_lineage,
			trace_id=None,
			policy_snapshot=None,
		)

	@classmethod
	async def _resolve_lineage_state(cls, db: AsyncSession, urn: str) -> tuple[LineageState, bool]:
		"""
		Calculates inherited properties using the Graph Engine.
		Uses Redis to cache the result of the recursive DB traversal.
		"""
		cache_key = f'lineage:state:{urn}'

		# A. Cache Hit
		cached = await cache.get_model(cache_key, LineageState)
		if cached:
			return cached, True

		# B. Cache Miss (Compute via Postgres Recursive CTE)
		provider = PostgresMetadataProvider(db)
		graph = LineageGraph(provider)

		# These calls now trigger SQL queries via the provider
		risk = await graph.get_inherited_risk(urn)
		sens = await graph.get_inherited_sensitivity(urn)
		poison = await graph.get_poisoned_constraints(urn)

		state = LineageState(inherited_risk=risk.value, inherited_sensitivity=sens.value, poisoned_constraints=poison)

		# Store with 5 min TTL
		await cache.set_model(cache_key, state, ttl_seconds=300)

		return state, False

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
		res_query = select(Resource).where(Resource.project_id == project_id, Resource.urn == urn)
		res_result = await db.execute(res_query)
		resource_obj = res_result.scalars().first()

		resource_tags = {}
		if resource_obj and resource_obj.attributes:
			resource_tags = resource_obj.attributes.get('tags', {})

		# 2. Fetch All Obligations for Project
		obl_query = select(ObligationModel).where(ObligationModel.project_id == project_id, ObligationModel.is_active)
		obl_result = await db.execute(obl_query)
		raw_obligations = obl_result.scalars().all()

		# 3. Match & Resolve
		pydantic_obs = [PydanticObligation(**ob.definition) for ob in raw_obligations]
		matched_obs = [ob for ob in pydantic_obs if cls._matcher.matches(urn, resource_tags, ob)]
		resolved_policy = cls._resolver.resolve(urn, matched_obs)

		# 4. Cache Result (TTL: 5 Minutes)
		await cache.set_model(cache_key, resolved_policy, ttl_seconds=300)

		return resolved_policy, False

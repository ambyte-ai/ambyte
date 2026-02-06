import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.audit import AuditLog
from src.db.models.inventory import Resource
from src.db.models.policy import Obligation
from src.schemas.stats import DashboardKPI, DashboardStatsResponse, DenyReasonAgg, RecentBlock, TrafficPoint

logger = logging.getLogger(__name__)


class StatsService:
	@classmethod
	async def get_dashboard_stats(
		cls, db: AsyncSession, project_id: UUID, lookback_hours: int = 24
	) -> DashboardStatsResponse:
		"""
		Aggregates all metrics required for the main dashboard in a few optimized queries.
		"""
		now = datetime.now(timezone.utc)
		start_time = now - timedelta(hours=lookback_hours)

		# ----------------------------------------------------------------------
		# 1. KPIs (Obligations & Resources)
		# ----------------------------------------------------------------------
		# Count Active Obligations
		stmt_obl = select(func.count(Obligation.id)).where(Obligation.project_id == project_id, Obligation.is_active)
		active_obligations = (await db.execute(stmt_obl)).scalar() or 0

		# Count Inventory Resources
		stmt_res = select(func.count(Resource.id)).where(Resource.project_id == project_id)
		protected_resources = (await db.execute(stmt_res)).scalar() or 0

		# Calculate Pending Ingestions from Redis
		# We scan keys created by the ingest-worker: 'ambyte:jobs:*'
		pending_ingestions = 0
		try:
			if cache.client:
				# Use scan_iter for safe iteration over keys
				# Note: In a high-scale production env, we would maintain a separate Redis Set of active job IDs TODO
				# to avoid scanning, but scanning with match is acceptable for the 24h TTL used by job_store.
				async for key in cache.client.scan_iter(match='ambyte:jobs:*'):
					raw_val = await cache.client.get(key)
					if raw_val:
						try:
							job_data = json.loads(raw_val)
							status = job_data.get('status', '')
							# Check if job is still active (Not COMPLETED or FAILED)
							if status and status not in ['COMPLETED', 'FAILED']:
								pending_ingestions += 1
						except (json.JSONDecodeError, TypeError):
							continue
		except Exception as e:
			logger.warning(f'Failed to calculate pending ingestions: {e}')
			# Fail open with 0 to not break dashboard
		# ----------------------------------------------------------------------
		# 2. Traffic Metrics (Last 24h)
		# ----------------------------------------------------------------------
		# We calculate total and denied in one pass
		stmt_logs = select(
			func.count(AuditLog.id).label('total'),
			func.sum(case((AuditLog.decision == 'DENY', 1), else_=0)).label('denied'),
		).where(AuditLog.project_id == project_id, AuditLog.timestamp >= start_time)

		result_logs = (await db.execute(stmt_logs)).one()
		total_reqs = result_logs.total or 0
		denied_reqs = result_logs.denied or 0

		# Calculate Rate (Prevent division by zero)
		allowed_reqs = total_reqs - denied_reqs
		enforcement_rate = 100.0
		if total_reqs > 0:
			enforcement_rate = (allowed_reqs / total_reqs) * 100.0

		kpi = DashboardKPI(
			total_requests_24h=total_reqs,
			denied_requests_24h=denied_reqs,
			enforcement_rate_24h=round(enforcement_rate, 1),
			active_obligations=active_obligations,
			protected_resources=protected_resources,
			pending_ingestions=pending_ingestions,
		)

		# ----------------------------------------------------------------------
		# 3. Time Series (Traffic Chart)
		# ----------------------------------------------------------------------
		# Bucket by Hour for the chart
		# Using Postgres date_trunc
		ts_bucket = func.date_trunc('hour', AuditLog.timestamp).label('bucket')

		stmt_series = (
			select(
				ts_bucket,
				func.sum(case((AuditLog.decision == 'ALLOW', 1), else_=0)).label('allowed'),
				func.sum(case((AuditLog.decision == 'DENY', 1), else_=0)).label('denied'),
			)
			.where(AuditLog.project_id == project_id, AuditLog.timestamp >= start_time)
			.group_by(ts_bucket)
			.order_by(ts_bucket)
		)

		series_res = await db.execute(stmt_series)

		traffic_series = []
		for row in series_res:
			traffic_series.append(
				TrafficPoint(timestamp=row.bucket, allowed_count=row.allowed or 0, denied_count=row.denied or 0)
			)

		# ----------------------------------------------------------------------
		# 4. Top Deny Reasons
		# ----------------------------------------------------------------------
		# Extract the 'decision_reason' from the JSONB column
		# Note: This relies on Postgres JSON functions.
		reason_expr = func.jsonb_extract_path_text(AuditLog.reason_trace, 'decision_reason')

		stmt_reasons = (
			select(reason_expr.label('reason'), func.count(AuditLog.id).label('deny_count'))
			.where(AuditLog.project_id == project_id, AuditLog.decision == 'DENY', AuditLog.timestamp >= start_time)
			.group_by('reason')
			.order_by(desc('deny_count'))
			.limit(5)
		)

		reasons_res = await db.execute(stmt_reasons)

		top_reasons = []
		for row in reasons_res:
			r_text = row.reason or 'Unspecified Policy'
			top_reasons.append(DenyReasonAgg(reason=r_text, count=row.deny_count))

		# ----------------------------------------------------------------------
		# 5. Recent Blocks (Stream)
		# ----------------------------------------------------------------------
		stmt_recent = (
			select(AuditLog)
			.where(AuditLog.project_id == project_id, AuditLog.decision == 'DENY')
			.order_by(AuditLog.timestamp.desc())
			.limit(10)
		)

		recent_res = await db.execute(stmt_recent)
		recent_blocks = []

		for log in recent_res.scalars():
			# Extract reason safely for the simplified view
			reason_txt = None
			if log.reason_trace:
				reason_txt = log.reason_trace.get('decision_reason')

			recent_blocks.append(
				RecentBlock(
					id=str(log.id),
					timestamp=log.timestamp,
					actor_id=log.actor_id,
					action=log.action,
					resource_urn=log.resource_urn,
					reason_summary=reason_txt,
				)
			)

		return DashboardStatsResponse(
			kpi=kpi, traffic_series=traffic_series, top_deny_reasons=top_reasons, recent_blocks=recent_blocks
		)

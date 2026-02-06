from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DashboardKPI(BaseModel):
	"""Headline metrics for the top row."""

	total_requests_24h: int
	denied_requests_24h: int
	enforcement_rate_24h: float = Field(..., description='Percentage of allowed requests (0-100)')
	active_obligations: int
	protected_resources: int
	pending_ingestions: int = Field(0, description='Number of PDF documents currently being processed.')


class TrafficPoint(BaseModel):
	"""A single data point for the main time-series chart."""

	timestamp: datetime
	allowed_count: int
	denied_count: int


class DenyReasonAgg(BaseModel):
	"""Aggregation for the Donut Chart."""

	reason: str
	count: int


class RecentBlock(BaseModel):
	"""Simplified log entry for the 'Recent Violations' list."""

	id: str
	timestamp: datetime
	actor_id: str
	action: str
	resource_urn: str
	reason_summary: str | None = None

	model_config = ConfigDict(from_attributes=True)


class DashboardStatsResponse(BaseModel):
	"""The root response object for GET /v1/stats/dashboard."""

	kpi: DashboardKPI
	traffic_series: list[TrafficPoint]
	top_deny_reasons: list[DenyReasonAgg]
	recent_blocks: list[RecentBlock]

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogCreate(BaseModel):
	"""
	Schema for ingesting an audit event.
	"""

	timestamp: datetime = Field(default_factory=datetime.utcnow)
	actor_id: str
	resource_urn: str
	action: str
	decision: str  # "ALLOW" or "DENY"

	# Detailed reasoning (optional, usually from DecisionEngine)
	reason_trace: dict[str, Any] | None = None

	# Snapshot of context (e.g. {region: "US"})
	request_context: dict[str, Any] | None = None


class BatchAuditLogCreate(BaseModel):
	"""
	For the bulk ingest endpoint.
	"""

	logs: list[AuditLogCreate]

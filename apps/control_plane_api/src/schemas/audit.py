from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PolicyContribution(BaseModel):
	"""
	A single obligation that contributed to a decision.
	Links audit logs back to specific policy sources for traceability.
	"""

	obligation_id: str = Field(..., description="The ID of the obligation (e.g., 'gdpr-art-17-retention').")
	source_id: str = Field(..., description="The human-readable source (e.g., 'GDPR-2016/679::Art.17').")
	effect: str = Field(..., description="The effect of this obligation: 'ALLOW' or 'DENY'.")
	reason: str = Field(..., description='Why this obligation contributed to the decision.')


class ReasonTrace(BaseModel):
	"""
	Structured trace linking decisions to policy sources.
	Enables forensic analysis and compliance auditing.
	"""

	decision_reason: str = Field(..., description='Primary reason for the decision.')
	cache_hit: bool = Field(False, description='Whether the decision was served from cache.')
	resolved_policy_hash: str | None = Field(None, description='Hash of ResolvedPolicy for reproducibility.')
	contributing_policies: list[PolicyContribution] = Field(
		default_factory=list, description='List of obligations that contributed to the decision.'
	)
	lineage_constraints: list[str] = Field(
		default_factory=list, description='Upstream poison pill constraints (e.g., "no-ai-training").'
	)


class AuditLogCreate(BaseModel):
	"""
	Schema for ingesting an audit event.
	"""

	timestamp: datetime = Field(default_factory=datetime.utcnow)
	actor_id: str
	resource_urn: str
	action: str
	decision: str  # "ALLOW" or "DENY"

	# Structured reasoning (optional, usually from DecisionEngine)
	reason_trace: ReasonTrace | None = None

	# Snapshot of context (e.g. {region: "US"})
	request_context: dict[str, Any] | None = None


class BatchAuditLogCreate(BaseModel):
	"""
	For the bulk ingest endpoint.
	"""

	logs: list[AuditLogCreate]


class AuditLogRead(AuditLogCreate):
	"""
	Output schema for listing logs.
	"""

	id: UUID
	project_id: UUID
	entry_hash: str
	block_id: UUID | None = None  # If present, log is sealed

	model_config = ConfigDict(from_attributes=True)

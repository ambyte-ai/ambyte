import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.schemas.audit import BatchAuditLogCreate
from src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
	'/',
	status_code=status.HTTP_202_ACCEPTED,  # 202 = Accepted for processing (buffered)
	summary='Ingest Audit Logs (Batch)',
	description='High-speed bulk ingestion endpoint. Writes to Redis Stream buffer for async persistence.',
	# Security: Only API Keys with 'audit:write' scope (or admin) can post here.
	dependencies=[Depends(VerifyScope(Scope.AUDIT_WRITE))],
)
async def ingest_audit_logs(
	payload: BatchAuditLogCreate,
	project: Annotated[Project, Depends(get_current_project)],
):
	"""
	Receives a list of audit events and buffers them to Redis Stream.
	This endpoint is designed for high-throughput, non-blocking usage by the SDK.

	The logs are buffered in Redis Streams and will be consumed by a background
	worker for durable persistence to Postgres. This decouples ingestion latency
	from database write latency.
	"""
	# Write to Redis Stream (sub-millisecond)
	count = await AuditService.log_batch_to_buffer(project.id, payload.logs)

	return {
		'ingested': count,
		'buffered': True,
		'message': f'{count} audit logs queued for processing.',
	}

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.audit import BatchAuditLogCreate
from src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
	'/',
	status_code=status.HTTP_201_CREATED,
	summary='Ingest Audit Logs (Batch)',
	description='Asynchronous bulk ingestion endpoint for SDK background workers.',
	# Security: Only API Keys with 'audit:write' scope (or admin) can post here.
	dependencies=[Depends(VerifyScope(Scope.AUDIT_WRITE))],
)
async def ingest_audit_logs(
	payload: BatchAuditLogCreate,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Receives a list of audit events and persists them to the database.
	This endpoint is designed for high-throughput, non-blocking usage by the SDK.
	"""
	# Delegate to the service layer for bulk insertion
	count = await AuditService.log_batch(db, project.id, payload.logs)

	return {'ingested': count}

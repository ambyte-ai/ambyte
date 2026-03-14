import logging
from typing import Annotated
from uuid import UUID

from ambyte_schemas.models.audit import AuditProof
from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.audit import AuditLogRead, BatchAuditLogCreate
from src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter()

# ==============================================================================
# Cryptography & Integrity
# ==============================================================================


class PublicKeyResponse(BaseModel):
	public_key: str


@router.get(
	'/public-key',
	response_model=PublicKeyResponse,
	summary='Get System Public Key',
	description='Returns the Ed25519 public key used to cryptographically verify audit block signatures.',
)
async def get_public_key():
	"""
	Exposes the Ambyte system public key.
	Users can use this key in the CLI (`ambyte audit verify`) to mathematically
	prove that their audit logs have not been tampered with.
	"""
	return {'public_key': 'dc68558900e06e39af21ac542ec6819c99f997114b028ef3024833ef5ccf158b'}


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


@router.get(
	'/proof/{log_id}',
	response_model=AuditProof,
	summary='Get Cryptographic Proof',
	description='Returns the Log Entry, the Signed Block Header, and the Merkle Path required to verify integrity.',
	# READ access required
	dependencies=[
		Depends(VerifyScope(Scope.AUDIT_WRITE))
	],  # Usually WRITE implies READ for audit in simple scopes, or add AUDIT_READ
)
async def get_audit_proof(
	log_id: Annotated[UUID, Path(title='The UUID of the log entry to verify')],
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Retrieves the verification bundle for a specific audit log.
	Allows clients to mathematically prove that the log exists in the immutable chain
	and has not been altered since sealing.
	"""
	return await AuditService.get_proof(db, project.id, log_id)


@router.get(
	'/',
	response_model=list[AuditLogRead],
	summary='List Audit Logs',
	description='Retrieve recent audit logs for the current project.',
	dependencies=[Depends(VerifyScope(Scope.AUDIT_WRITE))],  # Or define a new AUDIT_READ scope TODO
)
async def list_audit_logs(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
	limit: int = 50,
	actor_id: str | None = None,
	resource: str | None = None,
):
	return await AuditService.list_logs(db, project.id, limit=limit, actor_id=actor_id, resource_urn=resource)

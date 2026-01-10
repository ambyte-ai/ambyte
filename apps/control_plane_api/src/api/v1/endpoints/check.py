import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.audit import AuditLogCreate, ReasonTrace
from src.schemas.check import CheckRequest, CheckResponse
from src.services.audit_service import AuditService
from src.services.decision_service import DecisionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
	'/',
	summary='Check Permission',
	description='Evaluates whether an Actor can perform an Action on a Resource based on active policies.',
	response_model=CheckResponse,
	# Security: Must provide a valid API Key with 'check:write' scope
	dependencies=[Depends(VerifyScope('check:write'))],
)
async def check_access(
	payload: CheckRequest,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	The High-Performance Decision Point.
	"""
	# 1. Execute Decision Logic
	# This handles Redis caching, DB lookups, and Rule Resolution internally.
	result = await DecisionService.evaluate_access(db=db, project_id=project.id, req=payload)

	# 2. AUDIT LOGGING
	# This is enough for 99% of use-cases. For extreme scale, would use BackgroundTask or Kafka.
	try:
		log_entry = AuditLogCreate(
			timestamp=datetime.now(timezone.utc),
			actor_id=payload.actor_id or 'anonymous',
			resource_urn=payload.resource_urn,
			action=payload.action,
			decision='ALLOW' if result.allowed else 'DENY',
			# We store the reason string in the trace for simple debugging. TODO: Check this later.
			reason_trace=ReasonTrace(
				decision_reason=result.reason, cache_hit=result.cache_hit, resolved_policy_hash=None
			),
			request_context=payload.context,
		)
		# We await this to ensure it's durable.
		await AuditService.log_single(db, project.id, log_entry)

	except Exception as e:
		# FAIL OPEN for logging: Never break the application because logging failed
		logger.error(f'Failed to write audit log: {e}', exc_info=True)

	return result

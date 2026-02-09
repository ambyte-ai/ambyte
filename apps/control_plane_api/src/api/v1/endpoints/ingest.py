import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.schemas.ingest import IngestJobRead
from src.services.ingest_service import IngestService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
	'/jobs',
	response_model=list[IngestJobRead],
	summary='List Ingestion Jobs',
	description='Returns the status of recent background document processing tasks.',
	# We use POLICY_READ scope because these jobs result in policy creation
	dependencies=[Depends(VerifyScope(Scope.POLICY_READ))],
)
async def list_ingest_jobs(
	project: Annotated[Project, Depends(get_current_project)],
	limit: int = Query(50, ge=1, le=100, description='Max jobs to return'),
):
	"""
	Fetches the active ingestion queue from the shared state store (Redis).
	This allows the UI to show progress bars for PDF parsing and extraction.
	"""
	return await IngestService.get_recent_jobs(project.id, limit=limit)

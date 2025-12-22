import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.lineage import LineageEventCreate, LineageRunCreate
from src.services.lineage_service import LineageService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
	'/run',
	summary='Report Job Execution (Start/End)',
	description='Create or update the status of a data processing job (Run).',
	status_code=status.HTTP_200_OK,
	dependencies=[Depends(VerifyScope(Scope.LINEAGE_WRITE))],
)
async def report_run(
	payload: LineageRunCreate,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Called by the SDK when a traced block enters (Start) or exits (End).
	Idempotent based on `external_run_id`.
	"""
	run = await LineageService.upsert_run(db, project.id, payload)
	return {'id': run.id, 'status': 'recorded'}


@router.post(
	'/event',
	summary='Report Data Movement (Edges)',
	description='Record inputs and outputs associated with a specific Run.',
	status_code=status.HTTP_201_CREATED,
	dependencies=[Depends(VerifyScope(Scope.LINEAGE_WRITE))],
)
async def report_lineage_event(
	payload: LineageEventCreate,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Generates edges in the lineage graph (Source -> Target).
	Fails if the referenced `external_run_id` does not exist yet.
	"""
	count = await LineageService.create_events(db, project.id, payload)

	if count == 0 and (payload.inputs or payload.outputs):
		# for high-throughput ingestion, we often prefer 200 OK + log warning
		# to avoid crashing the client. We'll stick to 200 OK with count 0 here.
		pass

	return {'edges_created': count}

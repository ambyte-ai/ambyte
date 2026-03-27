import logging
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.lineage import LineageAnalysisResponse, LineageEventCreate, LineageGraphResponse, LineageRunCreate
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


@router.get(
	'/graph',
	summary='Get Lineage Topology',
	description='Returns the DAG of data assets, models, and execution runs for React Flow.',
	response_model=LineageGraphResponse,
	# Note: Re-using LINEAGE_WRITE as a generic Lineage access scope based on scopes.py
	dependencies=[Depends(VerifyScope(Scope.LINEAGE_WRITE))],
)
async def get_lineage_graph(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
	lookback_days: int = Query(30, ge=1, le=365, description='Filter edges by run start time'),
):
	"""
	Fetches the Data Lineage topology.
	Enriches the graph nodes with metadata from the Inventory service so the
	frontend can visually highlight risks, sensitivity, and 'Poison Pills'.
	"""
	return await LineageService.get_graph(db=db, project_id=project.id, lookback_days=lookback_days)


@router.get(
	'/analyze/{urn:path}',  # :path allows parsing URNs containing slashes (e.g. s3:// paths)
	summary='Analyze Node Lineage',
	description='Calculates inherited risk and traces poison pills for a specific asset.',
	response_model=LineageAnalysisResponse,
	dependencies=[Depends(VerifyScope(Scope.LINEAGE_WRITE))],
)
async def analyze_lineage_node(
	urn: str,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	The Diagnostic Endpoint.

	When a user clicks 'Trace Blocker' in the frontend, this endpoint executes a
	recursive graph traversal to find the exact origin of a compliance violation
	(the 'Poison Pill') and calculates the effective risk posture of the requested asset.
	"""
	# URNs in URLs might be URL-encoded, ensure it's safely decoded
	decoded_urn = urllib.parse.unquote(urn)

	return await LineageService.analyze_node(db=db, project_id=project.id, urn=decoded_urn)

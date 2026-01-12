from typing import Annotated

# Note: The response model is the Pydantic schema used by the SDK/CLI
# to ensure consistent serialization.
from ambyte_schemas.models.obligation import Obligation as ObligationSchema
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.policy import (
	BatchObligationCreate,
	ObligationFilter,
	PolicySummary,
)
from src.services.policy_service import PolicyService

router = APIRouter()


@router.put(
	'/',
	summary='Push Obligations (Bulk Upsert)',
	description="Create or update policies. Matches on the 'id' field (slug).",
	response_model=list[PolicySummary],
	# Requires 'policy:write' scope on the API Key
	dependencies=[Depends(VerifyScope('policy:write'))],
)
async def push_obligations(
	payload: BatchObligationCreate,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Handler for `ambyte push`.
	Takes a list of YAML-derived obligation objects and persists them.
	"""
	upserted = await PolicyService.upsert_batch(db=db, project_id=project.id, obligations=payload.obligations)

	# Service returns PolicySummary objects, which match the response model
	return upserted


@router.get(
	'/',
	summary='List Obligations',
	response_model=list[ObligationSchema],
	# Requires 'policy:read' scope
	dependencies=[Depends(VerifyScope('policy:read'))],
)
async def list_obligations(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
	filter_params: Annotated[ObligationFilter, Depends()],
):
	"""
	Fetch active obligations for the project.
	"""
	results = await PolicyService.get_all(db, project.id, filter_params)
	return [ObligationSchema(**obj.definition) for obj in results]


@router.get(
	'/{slug}',
	summary='Get Obligation by ID',
	response_model=ObligationSchema,
	dependencies=[Depends(VerifyScope('policy:read'))],
)
async def get_obligation(
	slug: str,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Retrieve a single policy definition.
	"""
	obj = await PolicyService.get_by_slug(db, project.id, slug)
	if not obj:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Obligation '{slug}' not found.")

	return ObligationSchema(**obj.definition)

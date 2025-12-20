from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.inventory import (
	BatchResourceCreate,
	ResourceResponse,
)
from src.services.inventory_service import InventoryService

router = APIRouter()


@router.put(
	'/',
	summary='Register Resources (Inventory Sync)',
	description='Bulk upsert of data assets discovered by connectors.',
	response_model=list[ResourceResponse],
	# Requires 'resource:write' scope (usually assigned to Connectors)
	dependencies=[Depends(VerifyScope('resource:write'))],
)
async def sync_inventory(
	payload: BatchResourceCreate,
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Handler for Connector syncs.
	Matches on URN. Overwrites metadata.
	"""
	upserted = await InventoryService.upsert_batch(db=db, project_id=project.id, resources=payload.resources)
	return upserted


@router.get(
	'/',
	summary='List Inventory',
	response_model=list[ResourceResponse],
	dependencies=[Depends(VerifyScope('resource:write'))],  # Write scope usually implies Read
)
async def list_resources(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Return all registered resources for the project.
	"""
	return await InventoryService.get_all(db, project.id)

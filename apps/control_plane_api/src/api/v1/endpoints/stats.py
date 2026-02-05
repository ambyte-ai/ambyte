from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_current_user, get_db
from src.db.models.auth import User
from src.db.models.tenancy import Project
from src.schemas.stats import DashboardStatsResponse
from src.services.stats_service import StatsService

router = APIRouter()


async def get_project_from_header(
	current_user: Annotated[User, Depends(get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
	x_ambyte_project_id: Annotated[str | None, Header()] = None,
) -> Project:
	"""
	Resolves the Project from the X-Ambyte-Project-Id header.
	Validates that the current user has access to it.
	"""
	if not x_ambyte_project_id:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Missing X-Ambyte-Project-Id header')

	try:
		project_uuid = UUID(x_ambyte_project_id)
	except ValueError as e:
		raise HTTPException(status_code=400, detail='Invalid Project ID format') from e

	# Reuse the logic from deps but adapted for Header
	stmt = select(Project).where(Project.id == project_uuid)
	result = await db.execute(stmt)
	project = result.scalars().first()

	if not project:
		raise HTTPException(status_code=404, detail='Project not found')

	# Enforce Tenant Isolation
	if not current_user.is_superuser and project.organization_id != current_user.organization_id:
		raise HTTPException(status_code=404, detail='Project not found')

	return project


@router.get(
	'/dashboard',
	response_model=DashboardStatsResponse,
	summary='Get Dashboard Metrics',
)
async def get_dashboard_stats(
	project: Annotated[Project, Depends(get_project_from_header)],
	db: Annotated[AsyncSession, Depends(get_db)],
	lookback_hours: int = Query(24, ge=1, le=168),
):
	stats = await StatsService.get_dashboard_stats(db=db, project_id=project.id, lookback_hours=lookback_hours)
	return stats

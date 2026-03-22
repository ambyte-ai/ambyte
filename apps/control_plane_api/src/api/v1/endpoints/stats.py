from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_current_project, get_db
from src.db.models.tenancy import Project
from src.schemas.stats import DashboardStatsResponse
from src.services.stats_service import StatsService

router = APIRouter()


@router.get(
	'/dashboard',
	response_model=DashboardStatsResponse,
	summary='Get Dashboard Metrics',
)
async def get_dashboard_stats(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
	lookback_hours: int = Query(24, ge=1, le=168),
):
	stats = await StatsService.get_dashboard_stats(db=db, project_id=project.id, lookback_hours=lookback_hours)
	return stats

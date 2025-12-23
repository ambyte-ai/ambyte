from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.db.models.auth import User
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.auth import ProjectBrief, UserRead, WhoAmIResponse

router = APIRouter()


@router.get('/whoami', response_model=WhoAmIResponse)
async def who_am_i(
	# This dependency validates the Clerk JWT and finds/creates the User in our DB
	current_user: Annotated[User, Depends(deps.get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Identity Verification Endpoint.
	Returns user profile details and all projects they have access to.
	"""

	# 1. Fetch all projects in the user's organization
	# In a more advanced RBAC system, we would filter by specific project memberships.
	# For now, we return all projects within their Org. TODO
	stmt = select(Project).where(Project.organization_id == current_user.organization_id).order_by(Project.name)
	result = await db.execute(stmt)
	projects = result.scalars().all()

	# 2. Build the structured response
	return WhoAmIResponse(
		user=UserRead(
			id=current_user.id,
			email=current_user.email,
			full_name=current_user.full_name,
			is_superuser=current_user.is_superuser,
		),
		organization_id=UUID(current_user.organization_id),
		organization_name=current_user.organization.name,
		projects=[ProjectBrief(id=p.id, name=p.name) for p in projects],
	)

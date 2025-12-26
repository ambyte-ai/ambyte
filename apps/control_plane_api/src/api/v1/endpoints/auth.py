from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.api import deps
from src.db.models.auth import User
from src.db.models.membership import ProjectMembership
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

	projects_with_roles: list[ProjectBrief] = []

	if current_user.is_superuser:
		# Superusers have access to all projects in the organization
		stmt = select(Project).where(Project.organization_id == current_user.organization_id).order_by(Project.name)
		result = await db.execute(stmt)
		projects = result.scalars().all()
		# Superusers get 'admin' role on all projects (virtual role)
		projects_with_roles = [ProjectBrief(id=p.id, name=p.name, role='admin') for p in projects]
	else:
		# Regular users only see projects where they have membership
		stmt = (
			select(ProjectMembership)
			.options(selectinload(ProjectMembership.project))
			.where(ProjectMembership.user_id == current_user.id)
			.order_by(ProjectMembership.project_id)
		)
		result = await db.execute(stmt)
		memberships = result.scalars().all()
		projects_with_roles = [ProjectBrief(id=m.project.id, name=m.project.name, role=m.role) for m in memberships]

	# Build the structured response
	return WhoAmIResponse(
		user=UserRead(
			id=current_user.id,
			email=current_user.email,
			full_name=current_user.full_name,
			is_superuser=current_user.is_superuser,
		),
		organization_id=UUID(current_user.organization_id),
		organization_name=current_user.organization.name,
		projects=projects_with_roles,
	)

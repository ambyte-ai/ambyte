from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.api.deps import get_current_user
from src.core import security
from src.db.models.auth import ApiKey
from src.db.models.membership import ProjectMembership
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.auth import ProjectBrief, UserRead, WhoAmIResponse

router = APIRouter()
security_scheme = HTTPBearer(auto_error=True)


@router.get('/whoami', response_model=WhoAmIResponse)
async def who_am_i(
	token_creds: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Identity Verification Endpoint.
	Supports both Human Users (Clerk JWT) and Machine Users (API Keys).
	"""
	token = token_creds.credentials

	# ==========================================================================
	# PATH A: API KEY (Machine)
	# ==========================================================================
	if token.startswith('sk_live_') or token.startswith('sk_test_'):
		key_hash = security.hash_token(token)

		# Fetch Key + Project + Organization
		# We need the deep nested Organization to fill the response
		stmt = (
			select(ApiKey)
			.where(ApiKey.key_hash == key_hash)
			.options(selectinload(ApiKey.project).selectinload(Project.organization))
		)
		result = await db.execute(stmt)
		api_key = result.scalars().first()

		if not api_key:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid API Key')

		project = api_key.project
		org = project.organization

		return WhoAmIResponse(
			user=UserRead(
				id=api_key.id,  # Use Key ID as the Actor ID
				email=f'machine-key-{api_key.prefix}...',  # Placeholder email
				full_name=api_key.name,
				is_superuser=False,
			),
			organization_id=org.id,
			organization_name=org.name,
			is_personal=org.external_id is None,
			# API Keys are scoped to a single project, so we return just that one
			projects=[ProjectBrief(id=project.id, name=project.name, role='machine_admin')],
		)
	# ==========================================================================
	# PATH B: JWT (Human)
	# ==========================================================================

	# We delegate to the dependency. This triggers the JIT logic in deps.py
	# which creates the User, Org, and Default Project if they don't exist.
	current_user = await get_current_user(token_creds, db)

	# Now that we have the user (newly created or existing), fetch their projects
	if current_user.is_superuser:
		stmt = select(Project).where(Project.organization_id == current_user.organization_id).order_by(Project.name)
		result = await db.execute(stmt)
		projects = result.scalars().all()
		projects_with_roles = [ProjectBrief(id=p.id, name=p.name, role='admin') for p in projects]
	else:
		stmt = (
			select(ProjectMembership)
			.options(selectinload(ProjectMembership.project))
			.where(ProjectMembership.user_id == current_user.id)
			.order_by(ProjectMembership.project_id)
		)
		result = await db.execute(stmt)
		memberships = result.scalars().all()
		projects_with_roles = [ProjectBrief(id=m.project.id, name=m.project.name, role=m.role) for m in memberships]

	return WhoAmIResponse(
		user=UserRead(
			id=current_user.id,
			email=current_user.email,
			full_name=current_user.full_name,
			is_superuser=current_user.is_superuser,
		),
		organization_id=UUID(str(current_user.organization_id)),
		organization_name=current_user.organization.name,
		is_personal=(current_user.organization.external_id is None),
		projects=projects_with_roles,
	)

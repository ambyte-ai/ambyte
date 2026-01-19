from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core import security
from src.db.models.auth import ApiKey, User
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
			# API Keys are scoped to a single project, so we return just that one
			projects=[ProjectBrief(id=project.id, name=project.name, role='machine_admin')],
		)
	# ==========================================================================
	# PATH B: JWT (Human)
	# ==========================================================================

	# 1. Verify Signature
	payload = await security.verify_clerk_token(token)
	if not payload:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail='Invalid or expired token',
			headers={'WWW-Authenticate': 'Bearer'},
		)

	external_id = payload.get('sub')
	if not external_id:
		raise HTTPException(status_code=401, detail='Token missing subject')

	# 2. Lookup User
	query = select(User).where(User.external_id == external_id).options(selectinload(User.organization))
	result = await db.execute(query)
	current_user = result.scalars().first()

	if not current_user:
		# Note: Full JIT provisioning logic (creating new users) is handled
		# by the browser flow or deps.get_current_user.
		# For CLI usage, we assume the user exists.
		raise HTTPException(status_code=401, detail='User not found in this organization')

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

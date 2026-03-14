from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.api.deps import get_current_user, get_current_user_project
from src.core import security
from src.core.cache import cache
from src.db.models.auth import ApiKey, User
from src.db.models.membership import ProjectMembership, ProjectRole
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.auth import ApiKeyCreate, ApiKeyRead, ApiKeySecret

router = APIRouter()

# ==============================================================================
# Helper Functions (RBAC)
# ==============================================================================


async def _enforce_role(db: AsyncSession, user: User, project_id: UUID, allowed_roles: set[str]):
	"""
	Ensures the current user has one of the allowed roles in the project.
	Superusers bypass this check.
	"""
	if user.is_superuser:
		return

	stmt = select(ProjectMembership).where(
		ProjectMembership.user_id == user.id, ProjectMembership.project_id == project_id
	)
	result = await db.execute(stmt)
	membership = result.scalars().first()

	if not membership or membership.role not in allowed_roles:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail='You do not have permission to perform this action in this project.',
		)


async def _prevent_last_owner_removal(db: AsyncSession, project_id: UUID, target_user_id: UUID):
	"""
	Prevents demoting or deleting the last OWNER of a project.
	"""
	# 1. Check if the target user is currently an owner
	stmt = select(ProjectMembership).where(
		ProjectMembership.user_id == target_user_id,
		ProjectMembership.project_id == project_id,
		ProjectMembership.role == ProjectRole.OWNER,
	)
	target_membership = (await db.execute(stmt)).scalars().first()

	if target_membership:
		# 2. Count total owners
		count_stmt = select(func.count(ProjectMembership.id)).where(
			ProjectMembership.project_id == project_id, ProjectMembership.role == ProjectRole.OWNER
		)
		owner_count = (await db.execute(count_stmt)).scalar() or 0

		if owner_count <= 1:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot remove or demote the last owner of a project.'
			)


# ==============================================================================
# API Key Management
# ==============================================================================


@router.post(
	'/{project_id}/keys',
	response_model=ApiKeySecret,
	summary='Generate a new API Key',
	description='Creates a machine credential for the SDK/CLI. Returns the raw secret once.',
)
async def create_api_key(
	project_id: UUID,
	payload: ApiKeyCreate,
	user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	await _enforce_role(db, user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.EDITOR})

	raw_key, key_hash = security.generate_api_key(prefix='sk_live_')

	db_obj = ApiKey(
		name=payload.name,
		prefix=raw_key[:10],
		key_hash=key_hash,
		scopes=payload.scopes,
		expires_at=payload.expires_at,
		project_id=project.id,
	)

	db.add(db_obj)
	await db.commit()
	await db.refresh(db_obj)

	return ApiKeySecret(key=raw_key, info=ApiKeyRead.model_validate(db_obj))


@router.get(
	'/{project_id}/keys',
	response_model=list[ApiKeyRead],
	summary='List API Keys',
)
async def list_api_keys(
	project_id: UUID,
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	stmt = select(ApiKey).where(ApiKey.project_id == project.id).order_by(ApiKey.created_at.desc())
	result = await db.execute(stmt)
	return result.scalars().all()


@router.delete(
	'/{project_id}/keys/{key_id}',
	status_code=status.HTTP_204_NO_CONTENT,
	summary='Revoke an API Key',
)
async def revoke_api_key(
	project_id: UUID,
	key_id: UUID,
	user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	await _enforce_role(db, user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.EDITOR})

	stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id)
	result = await db.execute(stmt)
	key = result.scalars().first()

	if not key:
		raise HTTPException(status_code=404, detail='API Key not found')

	await db.delete(key)
	await db.commit()


# ==============================================================================
# Project Management (CRUD)
# ==============================================================================


class ProjectCreate(BaseModel):
	name: str


class ProjectUpdate(BaseModel):
	name: str


class ProjectRead(BaseModel):
	id: UUID
	name: str
	created_at: datetime


@router.post('/', response_model=ProjectRead, status_code=201)
async def create_project(
	payload: ProjectCreate,
	user: Annotated[User, Depends(get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	new_project = Project(name=payload.name, organization_id=user.organization_id)
	db.add(new_project)
	await db.flush()

	# The creator is automatically the OWNER
	membership = ProjectMembership(user_id=user.id, project_id=new_project.id, role=ProjectRole.OWNER)
	db.add(membership)
	await db.commit()
	await db.refresh(new_project)

	return new_project


@router.get('/', response_model=list[ProjectRead])
async def list_projects(
	user: Annotated[User, Depends(get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	# Only return projects the user has membership in, unless superuser
	if user.is_superuser:
		stmt = select(Project).where(Project.organization_id == user.organization_id)
	else:
		stmt = (
			select(Project)
			.join(ProjectMembership)
			.where(Project.organization_id == user.organization_id, ProjectMembership.user_id == user.id)
		)
	result = await db.execute(stmt)
	return result.scalars().all()


@router.patch('/{project_id}', response_model=ProjectRead)
async def update_project(
	project_id: UUID,
	payload: ProjectUpdate,
	user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	await _enforce_role(db, user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN})

	project.name = payload.name
	await db.commit()
	await db.refresh(project)
	return project


@router.delete('/{project_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project_id: UUID,
	user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	# ONLY Owners can delete the entire project
	await _enforce_role(db, user, project.id, {ProjectRole.OWNER})

	await db.delete(project)
	await db.commit()


@router.head('/{project_id}/status', summary='Get Policy Version Hash')
async def get_policy_version(
	project_id: UUID,
	response: Response,
	project: Annotated[Project, Depends(get_current_user_project)],
):
	version = await cache.client.get(f'project_policy_version:{project.id}')
	if version:
		response.headers['X-Ambyte-Policy-Version'] = version
	else:
		response.headers['X-Ambyte-Policy-Version'] = ''
	return Response(status_code=status.HTTP_200_OK)


# ==============================================================================
# RBAC / Team Memberships
# ==============================================================================


class ProjectMemberRead(BaseModel):
	id: UUID
	user_id: UUID
	email: str
	full_name: str | None
	role: ProjectRole
	joined_at: datetime


class ProjectMemberCreate(BaseModel):
	email: EmailStr = Field(..., description='Email of an existing user in the organization')
	role: ProjectRole = Field(default=ProjectRole.VIEWER)


class ProjectMemberUpdate(BaseModel):
	role: ProjectRole


@router.get('/{project_id}/members', response_model=list[ProjectMemberRead])
async def list_project_members(
	project_id: UUID,
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	stmt = (
		select(ProjectMembership)
		.where(ProjectMembership.project_id == project.id)
		.options(selectinload(ProjectMembership.user))
		.order_by(ProjectMembership.created_at.asc())
	)
	result = await db.execute(stmt)
	memberships = result.scalars().all()

	return [
		ProjectMemberRead(
			id=m.id,
			user_id=m.user.id,
			email=m.user.email,
			full_name=m.user.full_name,
			role=m.role,
			joined_at=m.created_at,
		)
		for m in memberships
	]


@router.post('/{project_id}/members', response_model=ProjectMemberRead, status_code=201)
async def add_project_member(
	project_id: UUID,
	payload: ProjectMemberCreate,
	current_user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	await _enforce_role(db, current_user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN})

	# 1. Look up the target user by email within the SAME organization
	user_stmt = select(User).where(User.email == payload.email, User.organization_id == project.organization_id)
	target_user = (await db.execute(user_stmt)).scalars().first()

	if not target_user:
		raise HTTPException(
			status_code=404,
			detail='User not found in your organization. They must log in at least once to be provisioned.',
		)

	# 2. Check if they are already in the project
	mem_stmt = select(ProjectMembership).where(
		ProjectMembership.user_id == target_user.id, ProjectMembership.project_id == project.id
	)
	existing_mem = (await db.execute(mem_stmt)).scalars().first()

	if existing_mem:
		raise HTTPException(status_code=409, detail='User is already a member of this project.')

	# 3. Create membership
	new_mem = ProjectMembership(user_id=target_user.id, project_id=project.id, role=payload.role)
	db.add(new_mem)
	await db.commit()
	await db.refresh(new_mem)

	return ProjectMemberRead(
		id=new_mem.id,
		user_id=target_user.id,
		email=target_user.email,
		full_name=target_user.full_name,
		role=new_mem.role,
		joined_at=new_mem.created_at,
	)


@router.patch('/{project_id}/members/{user_id}', response_model=ProjectMemberRead)
async def update_project_member_role(
	project_id: UUID,
	user_id: UUID,
	payload: ProjectMemberUpdate,
	current_user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	await _enforce_role(db, current_user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN})

	# If demoting from OWNER, ensure they aren't the last one
	if payload.role != ProjectRole.OWNER:
		await _prevent_last_owner_removal(db, project.id, user_id)

	stmt = (
		select(ProjectMembership)
		.where(ProjectMembership.project_id == project.id, ProjectMembership.user_id == user_id)
		.options(selectinload(ProjectMembership.user))
	)
	membership = (await db.execute(stmt)).scalars().first()

	if not membership:
		raise HTTPException(status_code=404, detail='Membership not found.')

	membership.role = payload.role
	await db.commit()
	await db.refresh(membership)

	return ProjectMemberRead(
		id=membership.id,
		user_id=membership.user.id,
		email=membership.user.email,
		full_name=membership.user.full_name,
		role=membership.role,
		joined_at=membership.created_at,
	)


@router.delete('/{project_id}/members/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
	project_id: UUID,
	user_id: UUID,
	current_user: Annotated[User, Depends(get_current_user)],
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	# Admins can remove people, but if it's an Owner trying to leave, _prevent_last_owner_removal catches it
	await _enforce_role(db, current_user, project.id, {ProjectRole.OWNER, ProjectRole.ADMIN})
	await _prevent_last_owner_removal(db, project.id, user_id)

	stmt = select(ProjectMembership).where(
		ProjectMembership.project_id == project.id, ProjectMembership.user_id == user_id
	)
	membership = (await db.execute(stmt)).scalars().first()

	if not membership:
		raise HTTPException(status_code=404, detail='Membership not found.')

	await db.delete(membership)
	await db.commit()

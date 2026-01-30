from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_current_user, get_current_user_project
from src.core import security
from src.core.cache import cache
from src.db.models.auth import ApiKey, User
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.schemas.auth import ApiKeyCreate, ApiKeyRead, ApiKeySecret

router = APIRouter()

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
	# Auth: Ensures User owns this Project
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Generates a secure key (sk_live_...), hashes it, and stores the hash.
	"""
	# 1. Generate Credential
	# Prefix helps identify keys in logs (sk_live vs sk_test)
	raw_key, key_hash = security.generate_api_key(prefix='sk_live_')

	# 2. Persist
	db_obj = ApiKey(
		name=payload.name,
		prefix=raw_key[:10],  # Store "sk_live_ab..." for UI identification
		key_hash=key_hash,
		scopes=payload.scopes,
		expires_at=payload.expires_at,
		project_id=project.id,
	)

	db.add(db_obj)
	await db.commit()
	await db.refresh(db_obj)

	# 3. Return Raw Key (Only Time!)
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
	"""
	Returns metadata for all keys in the project. Does NOT return secrets.
	"""
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
	# Auth: Ensures User owns this Project
	project: Annotated[Project, Depends(get_current_user_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	Immediately invalidates an API Key by deleting it.
	"""
	# 1. Check existence & ownership
	# We must ensure the key actually belongs to the authorized project
	stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id)
	result = await db.execute(stmt)
	key = result.scalars().first()

	if not key:
		raise HTTPException(status_code=404, detail='API Key not found')

	# 2. Delete
	await db.delete(key)
	await db.commit()


# ==============================================================================
# Project Management (CRUD)
# ==============================================================================

# Minimal Project CRUD to support the UI workflow

from pydantic import BaseModel


class ProjectCreate(BaseModel):
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
	"""Create a new Project within the user's Organization."""
	new_project = Project(name=payload.name, organization_id=user.organization_id)
	db.add(new_project)
	await db.commit()
	await db.refresh(new_project)
	return new_project


@router.get('/', response_model=list[ProjectRead])
async def list_projects(
	user: Annotated[User, Depends(get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""List all projects in the user's Organization."""
	stmt = select(Project).where(Project.organization_id == user.organization_id)
	result = await db.execute(stmt)
	return result.scalars().all()


@router.head('/{project_id}/status', summary='Get Policy Version Hash')
async def get_policy_version(
	project_id: UUID,
	response: Response,
	project: Annotated[Project, Depends(get_current_user_project)],
):
	"""
	Returns the current policy version hash in the X-Ambyte-Policy-Version header.
	Useful for clients to efficiently check if policies have changed.
	"""
	version = await cache.client.get(f'project_policy_version:{project.id}')
	if version:
		response.headers['X-Ambyte-Policy-Version'] = version
	else:
		response.headers['X-Ambyte-Policy-Version'] = ''
	return Response(status_code=status.HTTP_200_OK)

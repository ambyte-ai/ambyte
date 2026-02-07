import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core import security
from src.core.cache import cache
from src.core.scopes import Scope
from src.db.models.auth import ApiKey, User
from src.db.models.membership import ProjectMembership, ProjectRole
from src.db.models.tenancy import Organization, Project
from src.db.session import get_db

logger = logging.getLogger(__name__)

# Standard Bearer Token scheme
# auto_error=True ensures FastAPI returns 401 if header is missing automatically
reusable_oauth2 = HTTPBearer(auto_error=True)


async def get_current_api_key(
	token: Annotated[HTTPAuthorizationCredentials, Security(reusable_oauth2)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKey:
	"""
	Low-level dependency: Validates hash and returns the ApiKey ORM object.
	Used for high-frequency SDK/CLI endpoints.
	"""
	raw_key = token.credentials

	# 1. Format Check (Fail fast)
	if not (raw_key.startswith('sk_live_') or raw_key.startswith('sk_test_') or raw_key.startswith('sk_ingest_')):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Invalid Key Format. Must start with 'sk_live_', 'sk_test_' or 'sk_ingest_'.",
		)

	# 2. Hash & Lookup
	key_hash = security.hash_token(raw_key)

	# Fetch Key + Project eagerly
	query = select(ApiKey).where(ApiKey.key_hash == key_hash).options(selectinload(ApiKey.project))
	result = await db.execute(query)
	api_key = result.scalars().first()

	# 3. Validation
	if not api_key:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Invalid Credentials')

	if api_key.expires_at:
		now = datetime.now(timezone.utc)
		expires = (
			api_key.expires_at.replace(tzinfo=timezone.utc) if api_key.expires_at.tzinfo is None else api_key.expires_at
		)
		if now > expires:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Key Expired')

	# 4. Usage Tracking (Best effort) - Using Redis for performance
	# We buffer last_used_at in Redis to avoid DB write pressure on every request.
	# A background job could sync these to the DB periodically if needed.
	try:
		usage_key = f'api_key_usage:{api_key.id}'
		now = datetime.now(timezone.utc)
		# Store timestamp in Redis with 1 hour TTL (will be refreshed on each use)
		if cache._redis:
			await cache._redis.set(usage_key, now.isoformat(), ex=3600)
	except Exception:
		logger.warning('Failed to update API Key last_used_at in Redis', exc_info=True)
		# Don't fail request on tracking error

	return api_key


async def get_current_project(api_key: Annotated[ApiKey, Depends(get_current_api_key)]) -> Project:
	"""
	High-level dependency: Returns the Project associated with the API Key.
	"""
	return api_key.project


class VerifyScope:
	"""
	Enforces that an API Key possesses a specific capability.

	Usage:
	    @router.post("/check", dependencies=[Depends(VerifyScope(Scope.CHECK_WRITE))])
	"""  # noqa: E101

	def __init__(self, required_scope: str):
		self.required_scope = required_scope

	def __call__(self, api_key: Annotated[ApiKey, Depends(get_current_api_key)]):
		"""
		FastAPI calls this method when evaluating the dependency.
		"""
		# 1. 'admin' scope is a wildcard that allows everything
		if Scope.ADMIN in api_key.scopes:
			return True

		# 2. Check for exact match
		if self.required_scope not in api_key.scopes:
			# We explicitly mention the missing scope to help developers debug
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail=f"Not authorized. API Key missing required scope: '{self.required_scope}'",
			)
		return True


# ==============================================================================
# Human Authentication (Clerk JWT)
# ==============================================================================


async def get_current_user(
	token: Annotated[HTTPAuthorizationCredentials, Security(reusable_oauth2)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
	"""
	Validates a JWT from Clerk, ensures the user exists in our DB,
	and returns the local User ORM object.
	"""
	# 1. Verify Signature (Remote JWKS)
	payload = await security.verify_clerk_token(token.credentials)
	if not payload:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail='Invalid or expired token',
			headers={'WWW-Authenticate': 'Bearer'},
		)

	# 2. Extract Claims
	# Clerk 'sub' is the unique user ID (e.g., "user_2pI...")
	external_id = payload.get('sub')
	if not external_id:
		raise HTTPException(status_code=401, detail='Token missing subject claim')

	# Get primary email if available
	email = payload.get('email')  # Check standard claim
	if not email:
		# Clerk often puts emails in a custom claim structure, handle fallback if needed
		# For now, we assume standard OIDC email claim is present via Clerk config
		email = f'{external_id}@placeholder.ambyte.ai'

	# 3. DB Lookup (The "Lazy Sync")
	# Check if we already know this user
	query = select(User).where(User.external_id == external_id).options(selectinload(User.organization))
	result = await db.execute(query)
	user = result.scalars().first()

	if user:
		return user

	# 4. First-Time User Registration (JIT Provisioning)
	# If the user is valid in Clerk but not in our DB, they just signed up.
	# We must assign them to an Organization.

	# Strategy:
	# A. Check if they have an 'org_id' in their Clerk metadata (Enterprise usage).
	# B. If not, create a default "Personal Organization" for them.

	# Check for Clerk organization ID in the JWT claims
	# Clerk sends org info in 'org_id' or nested in 'organizations' claim
	clerk_org_id = payload.get('org_id')

	target_org: Organization | None = None
	default_project: Project | None = None
	is_org_creator = False  # Track if this user is creating the org

	if clerk_org_id:
		# Enterprise flow: User belongs to a Clerk Organization
		# Look up existing org by external_id (Clerk org ID)
		org_query = select(Organization).where(Organization.external_id == clerk_org_id)
		org_result = await db.execute(org_query)
		target_org = org_result.scalars().first()

		if not target_org:
			# First user from this Clerk org - create the organization
			# Use org metadata from Clerk if available, else generate name
			org_name = payload.get('org_name', f'Organization {clerk_org_id[-8:]}')
			org_slug = payload.get('org_slug', f'org-{clerk_org_id[-8:]}')
			target_org = Organization(
				name=org_name,
				slug=org_slug,
				external_id=clerk_org_id,
			)
			db.add(target_org)
			await db.flush()  # Get ID for target_org

			# Create default project for new organization
			default_project = Project(name='Default Project', organization_id=target_org.id)
			db.add(default_project)
			await db.flush()
			is_org_creator = True
		else:
			# User joining existing org - find the default project
			project_query = select(Project).where(Project.organization_id == target_org.id).limit(1)
			project_result = await db.execute(project_query)
			default_project = project_result.scalars().first()

	else:
		# Self-serve flow: No Clerk org, create a personal organization
		target_org = Organization(
			name=f"{email}'s Organization",
			slug=f'org-{external_id[-8:]}',
			external_id=None,  # Personal orgs don't have Clerk org ID
		)
		db.add(target_org)
		await db.flush()

		# Create default project for personal org
		default_project = Project(name='Default Project', organization_id=target_org.id)
		db.add(default_project)
		await db.flush()
		is_org_creator = True

	# Create the user and assign to the organization
	new_user = User(
		email=email,
		external_id=external_id,
		organization_id=target_org.id,
		is_superuser=False,  # Default safe
	)
	db.add(new_user)
	await db.flush()  # Get user ID for membership

	# Create membership for the default project (if one exists)
	# Org creators get OWNER role, users joining existing orgs get EDITOR role
	if default_project:
		membership_role = ProjectRole.OWNER if is_org_creator else ProjectRole.EDITOR
		owner_membership = ProjectMembership(
			user_id=new_user.id,
			project_id=default_project.id,
			role=membership_role,
		)
		db.add(owner_membership)

	await db.commit()
	await db.refresh(new_user)

	# Manually populate the relationship to avoid MissingGreenlet error (lazy load in async)
	# unnecessary DB roundtrip since we already have the object
	new_user.organization = target_org

	return new_user


async def get_current_superuser(
	current_user: Annotated[User, Depends(get_current_user)],
) -> User:
	"""
	Authorization dependency for Platform Admins.
	"""
	if not current_user.is_superuser:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='The user does not have enough privileges')
	return current_user


# ==============================================================================
# HUMAN AUTH: Tenant Isolation (RBAC)
# ==============================================================================


async def get_current_user_project(
	project_id: Annotated[uuid.UUID, Path(title='The UUID of the project to access')],
	current_user: Annotated[User, Depends(get_current_user)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
	"""
	Validates that the Human User has access to the requested Project ID.

	This enforces Multi-Tenancy Isolation:
	- User must belong to the Organization that owns the Project.
	- OR User must be a Superuser (Platform Admin).
	"""

	# 1. Fetch Project
	query = select(Project).where(Project.id == project_id)
	result = await db.execute(query)
	project = result.scalars().first()

	# 2. Handle Not Found
	if not project:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Project not found')

	# 3. Enforce Isolation
	# Allow if Superuser OR if User's Org matches Project's Org
	has_access = current_user.is_superuser or (project.organization_id == current_user.organization_id)

	if not has_access:
		# Return 404 instead of 403 to prevent ID enumeration (leaking existence of other tenants' projects)
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Project not found')

	return project

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from src.core.config import settings
from src.db.models.auth import User
from src.db.session import AsyncSessionLocal
from svix.webhooks import Webhook, WebhookVerificationError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/clerk', status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(
	request: Request,
	svix_id: str = Header(alias='svix-id'),
	svix_timestamp: str = Header(alias='svix-timestamp'),
	svix_signature: str = Header(alias='svix-signature'),
):
	"""
	Handles user lifecycle events from Clerk (e.g., user.deleted).
	"""
	if not settings.CLERK_WEBHOOK_SECRET:
		logger.error('CLERK_WEBHOOK_SECRET is not set. Cannot verify webhook.')
		raise HTTPException(status_code=500, detail='Webhook configuration error')

	# 1. Get the raw body
	body_bytes = await request.body()

	# 2. Verify the Signature
	try:
		wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
		# svix.verify returns the parsed JSON payload if valid
		payload: dict[str, Any] = wh.verify(
			body_bytes, {'svix-id': svix_id, 'svix-timestamp': svix_timestamp, 'svix-signature': svix_signature}
		)
	except WebhookVerificationError as e:
		logger.warning('Invalid webhook signature attempt')
		raise HTTPException(status_code=400, detail='Invalid signature') from e

	# 3. Handle Events
	event_type = payload.get('type')
	data = payload.get('data', {})

	if event_type == 'user.deleted':
		await _handle_user_deleted(data)

	# Add other events here (e.g. user.updated) if needed

	return None


async def _handle_user_deleted(data: dict[str, Any]):
	"""
	Deletes the user from local Postgres.
	If the user belonged to a Personal Organization and is the last member,
	cleans up the entire organization (which cascades to projects, resources, etc).
	"""
	external_id = data.get('id')
	if not external_id:
		return

	logger.info(f'Processing deletion for user {external_id}')

	async with AsyncSessionLocal() as db:
		# 1. Fetch the user AND their organization before deleting
		stmt = select(User).options(selectinload(User.organization)).where(User.external_id == external_id)
		result = await db.execute(stmt)
		user = result.scalars().first()

		if not user:
			logger.info(f'User {external_id} not found in local database (already deleted?).')
			return

		org = user.organization
		org_id = org.id

		# In deps.py, personal orgs are created with external_id = None
		is_personal_org = org.external_id is None

		# 2. Delete the User
		# (This automatically deletes their ProjectMemberships via CASCADE)
		await db.delete(user)
		await db.flush()  # Flush to update the DB state without committing yet

		# 3. If it's a personal org, check if it's now empty
		if is_personal_org:
			count_stmt = select(func.count(User.id)).where(User.organization_id == org_id)
			remaining_users = await db.scalar(count_stmt)

			if remaining_users == 0:
				logger.info(f'Personal organization {org_id} is now empty. Deleting org and cascading data.')
				await db.delete(org)

		# 4. Commit the transaction
		await db.commit()
		logger.info(f'✅ User {external_id} deletion logic complete.')

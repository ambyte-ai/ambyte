import logging
from typing import Any, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import CursorResult, delete
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
	Your schema has ON DELETE CASCADE on memberships, so those will clean up automatically.
	"""
	external_id = data.get('id')
	if not external_id:
		return

	logger.info(f'Processing deletion for user {external_id}')

	async with AsyncSessionLocal() as db:
		# Delete user by external_id (Clerk ID)
		stmt = delete(User).where(User.external_id == external_id)
		result = cast(CursorResult, await db.execute(stmt))
		await db.commit()

		if result.rowcount > 0:
			logger.info(f'✅ User {external_id} deleted from local database.')
		else:
			logger.info(f'User {external_id} not found in local database (already deleted?).')

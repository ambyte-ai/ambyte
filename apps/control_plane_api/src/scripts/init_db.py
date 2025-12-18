import asyncio
import logging
import sys

from sqlalchemy import select
from src.core import security
from src.core.config import settings
from src.db.models.auth import ApiKey, User
from src.db.models.tenancy import Organization, Project
from src.db.session import AsyncSessionLocal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def init_db() -> None:
	async with AsyncSessionLocal() as db:
		logger.info('🌱 Starting database bootstrap...')

		# 1. Check if Superuser exists
		stmt = select(User).where(User.email == settings.FIRST_SUPERUSER)
		result = await db.execute(stmt)
		user = result.scalars().first()

		if user:
			logger.info(f'✅ Superuser {settings.FIRST_SUPERUSER} already exists. Skipping initialization.')
			return

		# 2. Create Default Organization
		logger.info('🏢 Creating default Organization...')
		org = Organization(name='Ambyte Platform Admin', slug='ambyte-admin')
		db.add(org)
		await db.flush()  # Flush to get org.id

		# 3. Create Superuser
		# Note: external_id is 'bootstrap' because this user bypasses Clerk for local admin tasks
		# or serves as a placeholder until the real Clerk user with this email signs up.
		logger.info(f'👤 Creating Superuser: {settings.FIRST_SUPERUSER}')
		user = User(
			email=settings.FIRST_SUPERUSER,
			full_name='Platform Administrator',
			external_id='bootstrap|admin',
			is_superuser=True,
			organization_id=org.id,
		)
		db.add(user)

		# 4. Create Default Project
		logger.info('📂 Creating Default Project...')
		project = Project(name='Default Workspace', organization_id=org.id)
		db.add(project)
		await db.flush()  # Flush to get project.id

		# 5. Generate Root API Key
		# This is the key you will use for your local CLI/SDK testing
		logger.info('🔑 Generating Root API Key...')

		raw_key, key_hash = security.generate_api_key(prefix='sk_live_')

		api_key = ApiKey(
			name='Bootstrap Admin Key',
			prefix=raw_key[:10],
			key_hash=key_hash,
			# Give full admin privileges
			scopes=['admin', 'check:write', 'audit:write', 'policy:write'],
			project_id=project.id,
		)
		db.add(api_key)

		await db.commit()

		# ======================================================================
		# OUTPUT
		# ======================================================================
		print('\n' + '=' * 60)
		print('🚀 AMBYTE PLATFORM INITIALIZED')
		print('=' * 60)
		print(f'Organization:  {org.name} ({org.id})')
		print(f'Project:       {project.name} ({project.id})')
		print(f'User:          {user.email}')
		print('-' * 60)
		print("YOUR API KEY (Copy this now, it won't be shown again):")
		print(f'\n👉  {raw_key}  👈\n')
		print('-' * 60)
		print('Usage in CLI:')
		print(f'export AMBYTE_API_KEY={raw_key}')
		print('ambyte check --resource urn:test ...')
		print('=' * 60 + '\n')


if __name__ == '__main__':
	asyncio.run(init_db())

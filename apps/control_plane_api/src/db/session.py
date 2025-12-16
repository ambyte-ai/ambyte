from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from src.core.config import settings

# ==============================================================================
# Async Engine Configuration
# ==============================================================================
engine = create_async_engine(
	str(settings.SQLALCHEMY_DATABASE_URI),
	# echo=True logs all SQL queries to stdout. Useful in local dev, noise in prod.
	echo=(settings.ENVIRONMENT == 'local'),
	# pool_pre_ping=True acts as a "heartbeat".
	# It catches dropped connections (e.g., database restarts) before handing them
	# to the application, preventing 500 errors.
	pool_pre_ping=True,
	# Tuning for High-Concurrency Policy Checks:
	# We increase the pool size because the Policy Engine needs to run many
	# lightweight SELECT queries in parallel.
	pool_size=20,
	max_overflow=10,
)

# ==============================================================================
# Session Factory
# ==============================================================================
# expire_on_commit=False is CRITICAL for async SQLAlchemy.
# Without it, accessing model attributes after a commit() forces an implicit
# IO refresh, which fails in async contexts because attributes aren't awaitable.
AsyncSessionLocal = async_sessionmaker(
	bind=engine,
	class_=AsyncSession,
	autoflush=False,
	expire_on_commit=False,
)


# ==============================================================================
# Dependency Injection
# ==============================================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
	"""
	FastAPI Dependency that yields a database session.
	Ensures the session is closed after the request is finished.
	"""
	async with AsyncSessionLocal() as session:
		yield session

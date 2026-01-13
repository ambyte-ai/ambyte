import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.v1.api import api_router
from src.core.cache import cache
from src.core.config import settings
from starlette.responses import RedirectResponse

if sys.platform == 'win32':
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
	level=settings.LOG_LEVEL,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""
	Lifecycle manager for the FastAPI app.
	Executed on startup (before receiving requests) and shutdown.
	"""
	await cache.connect()
	yield
	await cache.close()
	pass


app = FastAPI(
	title=settings.PROJECT_NAME,
	version=settings.VERSION,
	openapi_url=f'{settings.API_V1_STR}/openapi.json',
	lifespan=lifespan,
	# Disable docs in production for security (optional, based on preference)
	docs_url=None if settings.ENVIRONMENT == 'production' else '/docs',
	redoc_url=None if settings.ENVIRONMENT == 'production' else '/redoc',
)

# ==============================================================================
# Middleware
# ==============================================================================
if settings.BACKEND_CORS_ORIGINS:
	app.add_middleware(
		CORSMiddleware,
		allow_origins=[str(origin).rstrip('/') for origin in settings.BACKEND_CORS_ORIGINS],
		allow_credentials=True,
		allow_methods=['*'],
		allow_headers=['*'],
	)


# ==============================================================================
# Routes
# ==============================================================================


@app.get('/', include_in_schema=False)
def root():
	"""
	Redirect root to API documentation.
	"""
	return RedirectResponse(url='/docs')


@app.get('/ping', tags=['Health'])
def health_check():
	"""
	K8s / Docker Healthcheck endpoint.
	Used by load balancers to verify the service is up.
	"""
	return {'status': 'ok', 'env': settings.ENVIRONMENT, 'service': settings.PROJECT_NAME}


# ==============================================================================
# API Router Inclusion
# ==============================================================================

app.include_router(api_router, prefix=settings.API_V1_STR)

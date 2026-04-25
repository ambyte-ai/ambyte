from fastapi import APIRouter
from src.api.v1.endpoints import (
	audit,
	auth,
	check,
	ingest,
	lineage,
	obligations,
	opa,
	project,
	resources,
	stats,
	webhooks,
)

api_router = APIRouter()

# ==============================================================================
# Security & Tenancy
# ==============================================================================
api_router.include_router(auth.router, prefix='/auth', tags=['Authentication'])
api_router.include_router(project.router, prefix='/projects', tags=['Projects & API Keys'])

# ==============================================================================
# The Decision Engine
# ==============================================================================
api_router.include_router(check.router, prefix='/check', tags=['Decision Engine'])

# ==============================================================================
# Policy Management
# ==============================================================================
api_router.include_router(obligations.router, prefix='/obligations', tags=['Obligations'])
api_router.include_router(resources.router, prefix='/resources', tags=['Inventory'])

# ==============================================================================
# Observability
# ==============================================================================
api_router.include_router(audit.router, prefix='/audit', tags=['Audit Logs'])
api_router.include_router(lineage.router, prefix='/lineage', tags=['Data Lineage'])

# ==============================================================================
# Analytics & Insights
# ==============================================================================
api_router.include_router(stats.router, prefix='/stats', tags=['Analytics & Insights'])

# ==============================================================================
# Webhooks
# ==============================================================================
api_router.include_router(webhooks.router, prefix='/webhooks', tags=['Webhooks'])

# ==============================================================================
# Ingestion
# ==============================================================================
api_router.include_router(ingest.router, prefix='/ingest', tags=['Ingestion'])

# ==============================================================================
# OPA
# ==============================================================================
api_router.include_router(opa.router, prefix='/opa', tags=['OPA'])

from fastapi import APIRouter
from src.api.v1.endpoints import audit, auth, check, lineage, obligations, project, resources, stats, webhooks

api_router = APIRouter()

# ==============================================================================
# Security & Tenancy
# ==============================================================================
api_router.include_router(auth.router, prefix='/auth', tags=['Authentication'])
api_router.include_router(project.router, prefix='/projects', tags=['Projects & API Keys'])

# ==============================================================================
# The Decision Engine (Phase 5)
# ==============================================================================
api_router.include_router(check.router, prefix='/check', tags=['Decision Engine'])

# ==============================================================================
# Policy Management (Phase 4 - NOW LIVE)
# ==============================================================================
api_router.include_router(obligations.router, prefix='/obligations', tags=['Obligations'])
api_router.include_router(resources.router, prefix='/resources', tags=['Inventory'])

# ==============================================================================
# Observability (Phase 6)
# ==============================================================================
api_router.include_router(audit.router, prefix='/audit', tags=['Audit Logs'])
api_router.include_router(lineage.router, prefix='/lineage', tags=['Data Lineage'])

# ==============================================================================
# Analytics & Insights (Phase 7)
# ==============================================================================
api_router.include_router(stats.router, prefix='/stats', tags=['Analytics & Insights'])

# ==============================================================================
# Webhooks (Phase 8)
# ==============================================================================
api_router.include_router(webhooks.router, prefix='/webhooks', tags=['Webhooks'])

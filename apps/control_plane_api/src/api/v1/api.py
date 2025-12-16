from fastapi import APIRouter

# Placeholder imports for the endpoints we are about to build.
# As we build each module in Phase 4-6, these imports will become valid.
from src.api.v1.endpoints import (
	audit,
	auth,
	check,
	lineage,
	obligations,
	projects,
	resources,
)

api_router = APIRouter()

# ==============================================================================
# Security & Tenancy
# ==============================================================================
api_router.include_router(auth.router, prefix='/auth', tags=['Authentication'])
api_router.include_router(projects.router, prefix='/projects', tags=['Projects & API Keys'])

# ==============================================================================
# The Decision Engine (Critical Path)
# ==============================================================================
api_router.include_router(check.router, prefix='/check', tags=['Decision Engine'])

# ==============================================================================
# Policy Management (CRUD)
# ==============================================================================
api_router.include_router(obligations.router, prefix='/obligations', tags=['Obligations'])
api_router.include_router(resources.router, prefix='/resources', tags=['Inventory'])

# ==============================================================================
# Observability
# ==============================================================================
api_router.include_router(audit.router, prefix='/audit', tags=['Audit Logs'])
api_router.include_router(lineage.router, prefix='/lineage', tags=['Data Lineage'])

from fastapi import APIRouter

# Import the endpoints we have implemented
from src.api.v1.endpoints import audit, check, obligations, project, resources

# Placeholders for future phases (Uncomment as we build them)
# from src.api.v1.endpoints import auth, lineage

api_router = APIRouter()

# ==============================================================================
# Security & Tenancy
# ==============================================================================
# Auth router usually handles Login/SAML - to be built if not using pure API Keys/Clerk
# api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

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
# api_router.include_router(lineage.router, prefix="/lineage", tags=["Data Lineage"])

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import VerifyScope, get_current_project
from src.core.scopes import Scope
from src.db.models.tenancy import Project
from src.db.session import get_db
from src.services.opa_service import OpaService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
	'/bundle.tar.gz',
	summary='Download OPA Policy Bundle',
	description='Returns a dynamically compiled tar.gz bundle containing Rego policies and JSON data.',
	# Security: Requires 'policy:read' scope (standard for sidecars/agents)
	dependencies=[Depends(VerifyScope(Scope.POLICY_READ))],
)
async def get_opa_bundle(
	project: Annotated[Project, Depends(get_current_project)],
	db: Annotated[AsyncSession, Depends(get_db)],
):
	"""
	The Native OPA Bundle API endpoint.
	Configure your OPA sidecars to poll this URL. It will automatically return
	the latest executable tarball corresponding to your active legal obligations.
	"""
	# Generate or fetch cached Tarball bytes
	tarball_bytes = await OpaService.get_or_generate_bundle(db, project.id)

	# Return as a downloadable binary file
	return Response(
		content=tarball_bytes,
		media_type='application/gzip',
		headers={'Content-Disposition': f'attachment; filename="ambyte-opa-{project.id}.tar.gz"'},
	)

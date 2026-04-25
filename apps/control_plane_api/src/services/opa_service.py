import logging
import os
from pathlib import Path
from uuid import UUID

from ambyte_compiler.service import PolicyCompilerService
from ambyte_schemas.models.obligation import Obligation as PydanticObligation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.inventory import Resource
from src.db.models.policy import Obligation

logger = logging.getLogger(__name__)


class OpaService:
	"""
	Service for dynamically generating and caching Open Policy Agent (OPA) bundles.
	"""

	@classmethod
	async def get_or_generate_bundle(cls, db: AsyncSession, project_id: UUID) -> bytes:
		# 1. Resolve Cache Key based on Policy Version
		version = await cache.client.get(f'project_policy_version:{project_id}')
		version_str = version if version else 'initial'

		cache_key = f'opa_bundle:{project_id}:{version_str}'

		# 2. Check Cache
		cached_bundle = await cache.client.get(cache_key)
		if cached_bundle:
			logger.debug(f'Serving OPA bundle from cache for project {project_id}')
			return cached_bundle

		logger.info(f'Cache miss for OPA bundle. Compiling policies for project {project_id}...')

		# 3. Fetch Active Obligations
		obs_query = select(Obligation).where(Obligation.project_id == project_id, Obligation.is_active)
		obs_result = await db.execute(obs_query)
		pydantic_obs = [PydanticObligation(**ob.definition) for ob in obs_result.scalars().all()]

		# 4. Fetch Resource Inventory
		res_query = select(Resource).where(Resource.project_id == project_id)
		res_result = await db.execute(res_query)
		resources = [{'urn': r.urn, 'tags': r.attributes.get('tags', {})} for r in res_result.scalars().all()]

		# 5. Initialize Compiler
		# Resolve templates path. In Docker, it's /app/policy-library/sql_templates
		# Locally, we traverse up from this file's location.
		default_path = Path(__file__).parents[5] / 'policy-library' / 'sql_templates'
		base_path = Path(os.getenv('AMBYTE_TEMPLATES_PATH', default_path)).resolve()

		compiler = PolicyCompilerService(templates_path=base_path)

		# 6. Compile individual data payloads
		master_bundle = {}
		for res in resources:
			try:
				data = compiler.compile(resources=[res], obligations=pydantic_obs, target='opa')
				if isinstance(data, dict):
					master_bundle[res['urn']] = data
			except Exception as e:
				logger.warning(f'Failed to compile OPA rule for {res["urn"]}: {e}')

		# Wrap in the namespace expected by main.rego
		wrapped_data = {'ambyte': {'policies': master_bundle}}

		# 7. Package the Tarball
		tarball_bytes = compiler.build_opa_tarball(wrapped_data)

		# 8. Cache & Return
		# We cache it for a long time since the cache key changes automatically when a policy updates
		await cache.client.set(cache_key, tarball_bytes, ex=86400)  # 24 hours

		return tarball_bytes

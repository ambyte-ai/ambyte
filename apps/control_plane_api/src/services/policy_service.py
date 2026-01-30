import hashlib
import json
import logging
from uuid import UUID, uuid4

from ambyte_schemas.models.obligation import Obligation as PydanticObligation
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.policy import Obligation as ObligationModel
from src.schemas.policy import ObligationFilter, PolicySummary

logger = logging.getLogger(__name__)


class PolicyService:
	"""
	Business logic for managing Obligations (Policies).
	Handles hashing, versioning, pruning, and dry-run simulations.
	"""

	@staticmethod
	def _calculate_hash(definition: dict) -> str:
		"""
		Generates a deterministic SHA-256 hash of the policy definition.
		"""
		# We sort keys to ensure identical YAMLs with different key orders match.
		encoded_str = json.dumps(definition, sort_keys=True).encode('utf-8')
		return hashlib.sha256(encoded_str).hexdigest()

	@classmethod
	async def upsert_batch(
		cls,
		db: AsyncSession,
		project_id: UUID,
		obligations: list[PydanticObligation],
		prune: bool = False,
		dry_run: bool = False,
	) -> list[PolicySummary]:
		"""
		Synchronize local obligations with the database.

		Returns a list of PolicySummary objects describing the changes.
		"""
		if not obligations and not prune:
			return []

		# 1. Fetch Existing State
		# We need to know what's already there to calculate deltas
		stmt = select(ObligationModel).where(ObligationModel.project_id == project_id, ObligationModel.is_active)
		result = await db.execute(stmt)
		existing_map = {obj.slug: obj for obj in result.scalars().all()}

		incoming_slugs = [ob.id for ob in obligations]
		summary_report: list[PolicySummary] = []
		upsert_values = []

		# 2. Process Incoming Obligations
		for ob in obligations:
			definition_json = ob.model_dump(mode='json', exclude_none=True)
			new_hash = cls._calculate_hash(definition_json)

			existing = existing_map.get(ob.id)

			status = 'UNCHANGED'
			version = 1

			if not existing:
				status = 'CREATED'
				version = 1
			elif existing.source_hash != new_hash:
				status = 'UPDATED'
				version = existing.version + 1
			else:
				# Matches existing hash
				status = 'UNCHANGED'
				version = existing.version

			summary_report.append(PolicySummary(slug=ob.id, title=ob.title, status=status, version=version))

			# Prepare DB row
			upsert_values.append(
				{
					'project_id': project_id,
					'slug': ob.id,
					'title': ob.title,
					'enforcement_level': ob.enforcement_level.name
					if hasattr(ob.enforcement_level, 'name')
					else str(ob.enforcement_level),
					'definition': definition_json,
					'source_hash': new_hash,
					'version': version,
					'is_active': True,
				}
			)

		# 3. Process Pruning (Identify local deletions)
		prune_slugs = []
		if prune:
			for slug, existing_obj in existing_map.items():
				if slug not in incoming_slugs:
					prune_slugs.append(slug)
					summary_report.append(
						PolicySummary(
							slug=slug, title=existing_obj.title, status='PRUNED', version=existing_obj.version
						)
					)

		# 4. Persistence (Skip if Dry Run)
		if not dry_run:
			if upsert_values:
				# Execute Bulk Upsert
				stmt = insert(ObligationModel).values(upsert_values)
				update_stmt = stmt.on_conflict_do_update(
					index_elements=['project_id', 'slug'],
					set_={
						'title': stmt.excluded.title,
						'enforcement_level': stmt.excluded.enforcement_level,
						'definition': stmt.excluded.definition,
						'source_hash': stmt.excluded.source_hash,
						'version': stmt.excluded.version,
						'is_active': stmt.excluded.is_active,
						'updated_at': func.now(),
					},
					# Only touch rows where hash actually changed or we are re-activating
					where=(
						(ObligationModel.source_hash != stmt.excluded.source_hash)
						| (ObligationModel.is_active.is_(False))
					),
				)
				await db.execute(update_stmt)

			if prune_slugs:
				# Deactivate pruned policies
				prune_stmt = (
					update(ObligationModel)
					.where(ObligationModel.project_id == project_id)
					.where(ObligationModel.slug.in_(prune_slugs))
					.values(is_active=False, updated_at=func.now())
				)
				await db.execute(prune_stmt)

			await db.commit()

			# Invalidate Caches for this project
			await cache.delete_pattern(f'decision:{project_id}:*')

			# Update the policy version key for this project
			await cache.client.set(f'project_policy_version:{project_id}', str(uuid4()))

			logger.info(f'Sync complete for project {project_id}. Delta: {len(summary_report)} items.')
		else:
			logger.info(f'Dry run simulation for project {project_id}. No changes committed.')

		return summary_report

	@staticmethod
	async def get_all(
		db: AsyncSession, project_id: UUID, filters: ObligationFilter | None = None
	) -> list[ObligationModel]:
		"""
		List obligations with optional filtering.
		"""
		stmt = select(ObligationModel).where(ObligationModel.project_id == project_id, ObligationModel.is_active)

		if filters:
			if filters.enforcement_level:
				stmt = stmt.where(ObligationModel.enforcement_level == filters.enforcement_level.name)
			if filters.query:
				search = f'%{filters.query}%'
				stmt = stmt.where((ObligationModel.title.ilike(search)) | (ObligationModel.slug.ilike(search)))

		stmt = stmt.order_by(ObligationModel.slug.asc())
		result = await db.execute(stmt)
		return list(result.scalars().all())

	@staticmethod
	async def get_by_slug(db: AsyncSession, project_id: UUID, slug: str) -> ObligationModel | None:
		"""
		Retrieve a single obligation definition.
		"""
		stmt = select(ObligationModel).where(ObligationModel.project_id == project_id, ObligationModel.slug == slug)
		result = await db.execute(stmt)
		return result.scalars().first()

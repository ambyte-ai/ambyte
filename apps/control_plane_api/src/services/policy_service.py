from uuid import UUID

from ambyte_schemas.models.obligation import Obligation as PydanticObligation
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.policy import Obligation as ObligationModel
from src.schemas.policy import ObligationFilter


class PolicyService:
	"""
	Business logic for managing Obligations (Policies).
	Handles mapping between strict Pydantic schemas and the JSONB-heavy Database model.
	"""

	@staticmethod
	async def upsert_batch(
		db: AsyncSession, project_id: UUID, obligations: list[PydanticObligation]
	) -> list[ObligationModel]:
		"""
		Create or Update obligations in bulk.
		Uses PostgreSQL native ON CONFLICT logic for atomicity and performance.
		"""
		if not obligations:
			return []

		# 1. Prepare Data for Bulk Insert
		# We transform the Pydantic objects into dictionaries matching the DB schema.
		values = []
		slugs = []

		for ob in obligations:
			# We explicitly exclude None to save DB space and keep the JSON clean
			definition_json = ob.model_dump(mode='json', exclude_none=True)

			values.append(
				{
					'project_id': project_id,
					# Map Pydantic 'id' (from YAML) to DB 'slug' (logical unique identifier)
					'slug': ob.id,
					'title': ob.title,
					# Enum value is stored as string for easier SQL querying
					'enforcement_level': ob.enforcement_level.name
					if hasattr(ob.enforcement_level, 'name')
					else str(ob.enforcement_level),
					'definition': definition_json,
					'source_hash': None,  # TODO: Add hashing logic for change detection
					'is_active': True,
				}
			)
			slugs.append(ob.id)

		# 2. Construct the Upsert Statement
		stmt = insert(ObligationModel).values(values)

		# Defines what happens if (project_id, slug) already exists
		update_stmt = stmt.on_conflict_do_update(
			# This requires a UniqueConstraint on (project_id, slug) in the DB
			index_elements=['project_id', 'slug'],
			set_={
				'title': stmt.excluded.title,
				'enforcement_level': stmt.excluded.enforcement_level,
				'definition': stmt.excluded.definition,
				'updated_at': func.now(),
				'is_active': True,
			},
		)

		# 3. Execute
		await db.execute(update_stmt)
		await db.commit()

		# 4. Return the refreshed objects
		# We fetch them back to return standardized ORM objects with system IDs
		query = select(ObligationModel).where(ObligationModel.project_id == project_id, ObligationModel.slug.in_(slugs))
		result = await db.execute(query)
		return list(result.scalars().all())

	@staticmethod
	async def get_all(
		db: AsyncSession, project_id: UUID, filters: ObligationFilter | None = None
	) -> list[ObligationModel]:
		"""
		List obligations with optional filtering.
		"""
		stmt = select(ObligationModel).where(ObligationModel.project_id == project_id)

		if filters:
			if filters.enforcement_level:
				# Filter by the string column
				level_str = filters.enforcement_level.name
				stmt = stmt.where(ObligationModel.enforcement_level == level_str)

			if filters.query:
				# Case-insensitive search on Title or Slug
				search = f'%{filters.query}%'
				stmt = stmt.where((ObligationModel.title.ilike(search)) | (ObligationModel.slug.ilike(search)))

		stmt = stmt.order_by(ObligationModel.created_at.desc())
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

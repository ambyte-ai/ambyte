from math import ceil
from uuid import UUID

from ambyte_schemas.models.common import PaginatedResponse
from ambyte_schemas.models.inventory import ResourceCreate, ResourceResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.inventory import Resource as ResourceModel


class InventoryService:
	"""
	Business logic for managing Data Resources (Inventory).
	Handled primarily by automated Connectors via the API.
	"""

	@staticmethod
	async def upsert_batch(db: AsyncSession, project_id: UUID, resources: list[ResourceCreate]) -> list[ResourceModel]:
		"""
		Create or Update resources in bulk.
		Target: UniqueConstraint(project_id, urn)
		"""
		if not resources:
			return []

		# 1. Prepare Data
		values = []
		urns = []

		for res in resources:
			values.append(
				{
					'project_id': project_id,
					'urn': res.urn,
					'platform': res.platform,
					'name': res.name,
					'attributes': res.attributes,
				}
			)
			urns.append(res.urn)

		# 2. Construct Upsert Statement
		stmt = insert(ResourceModel).values(values)

		update_stmt = stmt.on_conflict_do_update(
			# Target the unique constraint name explicitly if possible,
			# or use index_elements for standard column sets.
			# Using index_elements matches the UniqueConstraint(project_id, urn) logic.
			index_elements=['project_id', 'urn'],
			set_={'name': stmt.excluded.name, 'attributes': stmt.excluded.attributes, 'updated_at': func.now()},
		)

		# 3. Execute
		await db.execute(update_stmt)
		await db.commit()

		for urn in urns:
			await cache.delete_pattern(f'decision:{project_id}:{urn}')

		# 4. Fetch and return refreshed objects
		query = select(ResourceModel).where(ResourceModel.project_id == project_id, ResourceModel.urn.in_(urns))
		result = await db.execute(query)
		return list(result.scalars().all())

	@staticmethod
	async def get_all(
		db: AsyncSession, project_id: UUID, page: int = 1, size: int = 50
	) -> PaginatedResponse[ResourceResponse]:
		"""
		List all resources for a project with pagination.
		"""
		if page < 1:
			page = 1
		if size > 100:
			size = 100

		# 1. Base Query
		stmt = select(ResourceModel).where(ResourceModel.project_id == project_id)

		# 2. Total Count
		count_stmt = select(func.count()).select_from(stmt.subquery())
		total = (await db.execute(count_stmt)).scalar_one()

		# 3. Data Query
		# Apply ordering, limit, offset
		data_stmt = stmt.order_by(ResourceModel.urn).limit(size).offset((page - 1) * size)
		result = await db.execute(data_stmt)
		orm_items = result.scalars().all()

		# 4. Map to Pydantic
		items = [ResourceResponse.model_validate(item) for item in orm_items]

		# 5. Calculate pages
		pages = ceil(total / size) if size > 0 else 0

		return PaginatedResponse(
			items=items,
			total=total,
			page=page,
			size=size,
			pages=pages,
		)

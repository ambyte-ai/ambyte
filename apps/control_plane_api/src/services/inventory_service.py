from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.inventory import Resource as ResourceModel
from src.schemas.inventory import ResourceCreate


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
	async def get_all(db: AsyncSession, project_id: UUID) -> list[ResourceModel]:
		"""
		List all resources for a project.
		TODO: Add pagination for large inventories.
		"""
		stmt = select(ResourceModel).where(ResourceModel.project_id == project_id).order_by(ResourceModel.urn)

		result = await db.execute(stmt)
		return list(result.scalars().all())

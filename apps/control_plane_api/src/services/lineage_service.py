import logging
from datetime import datetime, timezone
from uuid import UUID

from ambyte_schemas.models.lineage import RunType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.cache import cache
from src.db.models.lineage import LineageEdge, LineageRun
from src.schemas.lineage import LineageEventCreate, LineageRunCreate

logger = logging.getLogger(__name__)


class LineageService:
	"""
	Manages the Data Lineage Graph.
	Handles lifecycle events (Run Start/End) and Data Movement events (Edges).
	"""

	@staticmethod
	async def upsert_run(db: AsyncSession, project_id: UUID, payload: LineageRunCreate) -> LineageRun:
		"""
		Create or Update a Lineage Run.
		The SDK calls this twice: once at start, once at completion.
		"""
		# 1. Check for existing run
		query = select(LineageRun).where(
			LineageRun.project_id == project_id, LineageRun.external_run_id == payload.external_run_id
		)
		result = await db.execute(query)
		run = result.scalars().first()

		if run:
			# UPDATE CASE (Job Finished)
			if payload.ended_at:
				run.ended_at = payload.ended_at
				run.success = payload.success

			# Allow updating type/start_time if they arrived late or changed
			if payload.started_at:
				run.started_at = payload.started_at
			if payload.run_type != RunType.UNSPECIFIED:
				run.run_type = payload.run_type.name

			# Mark as modified
			db.add(run)
		else:
			# CREATE CASE (Job Started)
			# Ensure we have a start time, default to now if missing (e.g. out of order)
			start_time = payload.started_at or datetime.now(timezone.utc)

			run = LineageRun(
				project_id=project_id,
				external_run_id=payload.external_run_id,
				# Store Enum as String
				run_type=payload.run_type.name,
				started_at=start_time,
				ended_at=payload.ended_at,
				success=payload.success,
			)
			db.add(run)

		await db.commit()
		await db.refresh(run)
		return run

	@staticmethod
	async def create_events(db: AsyncSession, project_id: UUID, payload: LineageEventCreate) -> int:
		"""
		Records data movement (Inputs -> Outputs).
		Generates edges in the graph connecting Source URNs to Target URNs via the Run.
		"""
		# 1. Resolve the internal Run ID
		query = select(LineageRun).where(
			LineageRun.project_id == project_id, LineageRun.external_run_id == payload.external_run_id
		)
		result = await db.execute(query)
		run = result.scalars().first()

		if not run:
			logger.warning(f'Received lineage event for unknown run_id: {payload.external_run_id}')
			return 0

		# 2. Generate Edges (Cartesian Product)
		# Represents that data flowed from every Input to every Output during this run.
		# If inputs or outputs are empty, no direct edges are created, but the Run exists as a record.
		edges = []
		affected_targets = set()

		for source_urn in payload.inputs:
			for target_urn in payload.outputs:
				edges.append(
					LineageEdge(
						project_id=project_id,
						run_id=run.id,
						source_urn=source_urn,
						target_urn=target_urn,
					)
				)
				affected_targets.add(target_urn)

		if not edges:
			return 0

		# 3. Bulk Insert
		db.add_all(edges)
		await db.commit()

		# 4. Cache Invalidation
		if cache.client:
			for urn in affected_targets:
				# Pattern matches the key used in DecisionService
				key = f'lineage:state:{urn}'
				await cache.client.delete(key)

			logger.debug(f'Invalidated lineage cache for {len(affected_targets)} targets.')

		count = len(edges)
		logger.debug(f'Created {count} lineage edges for run {payload.external_run_id}')
		return count

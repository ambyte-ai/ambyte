import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ambyte_rules.lineage import LineageGraph
from ambyte_schemas.models.lineage import RunType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.cache import cache
from src.db.models.inventory import Resource
from src.db.models.lineage import LineageEdge, LineageRun
from src.schemas.lineage import (
	GraphEdge,
	GraphNode,
	LineageAnalysisResponse,
	LineageEventCreate,
	LineageGraphResponse,
	LineageRunCreate,
)
from src.services.lineage_graph_adapter import PostgresMetadataProvider

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
				triggered_by=payload.triggered_by,
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

	@staticmethod
	async def get_graph(db: AsyncSession, project_id: UUID, lookback_days: int = 30) -> LineageGraphResponse:
		"""
		Constructs the Lineage DAG for the frontend.
		Joins Lineage Edges/Runs with Inventory Resources to enrich the nodes.
		"""
		cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

		# 1. Fetch Edges and their associated Runs
		edges_stmt = (
			select(LineageEdge)
			.join(LineageEdge.run)
			.where(LineageEdge.project_id == project_id, LineageRun.started_at >= cutoff_date)
			.options(selectinload(LineageEdge.run))
		)

		edges_result = await db.execute(edges_stmt)
		db_edges = edges_result.scalars().all()

		if not db_edges:
			return LineageGraphResponse(nodes=[], edges=[])

		# 2. Extract unique URNs to fetch Node metadata
		unique_urns = set()
		for edge in db_edges:
			unique_urns.add(edge.source_urn)
			unique_urns.add(edge.target_urn)

		# 3. Fetch Inventory Resources for Enrichment
		# We chunk the URNs just in case there are thousands, but usually .in_() is fine
		res_stmt = select(Resource).where(Resource.project_id == project_id, Resource.urn.in_(unique_urns))
		res_result = await db.execute(res_stmt)
		resources_map = {r.urn: r for r in res_result.scalars().all()}

		# 4. Construct Frontend Nodes
		nodes = []
		for urn in unique_urns:
			resource = resources_map.get(urn)

			if resource:
				# Node exists in Inventory
				attrs = resource.attributes or {}

				# Check root attribute first, fallback to nested tags
				sens = str(attrs.get('sensitivity', 'UNSPECIFIED')).upper()
				if sens == 'UNSPECIFIED':
					sens = str(attrs.get('tags', {}).get('sensitivity', 'UNSPECIFIED')).upper()

				risk = str(attrs.get('risk_level', 'UNSPECIFIED')).upper()
				if risk == 'UNSPECIFIED':
					risk = str(attrs.get('tags', {}).get('risk_level', 'UNSPECIFIED')).upper()

				# Determine AI Restriction (The "Poison Pill")
				# Look for explicit ai_training_allowed=False or specific tags
				is_restricted = attrs.get('ai_training_allowed') is False

				nodes.append(
					GraphNode(
						id=urn,
						label=resource.name or urn.split(':')[-1],
						platform=resource.platform,
						node_type='model' if 'model' in urn.lower() else 'resource',
						sensitivity=sens,
						risk_level=risk,
						tags=attrs.get('tags', {}),
						is_ai_restricted=is_restricted,
					)
				)
			else:
				# Node is external/unregistered (e.g., an external S3 bucket, or a user download)
				platform_hint = urn.split(':')[2] if len(urn.split(':')) > 2 else 'unknown'
				nodes.append(
					GraphNode(
						id=urn,
						label=urn.split(':')[-1],
						platform=platform_hint,
						node_type='model' if 'model' in urn.lower() else 'resource',
					)
				)

		# 5. Construct Frontend Edges
		edges = []
		for edge in db_edges:
			run = edge.run
			edges.append(
				GraphEdge(
					id=str(edge.id),
					source=edge.source_urn,
					target=edge.target_urn,
					run_id=run.external_run_id,
					run_type=run.run_type,
					success=run.success,
					# Safe fallback if actor wasn't captured
					actor_id=run.triggered_by if run.triggered_by else 'system',
					start_time=run.started_at,
				)
			)

		return LineageGraphResponse(nodes=nodes, edges=edges)

	@staticmethod
	async def analyze_node(db: AsyncSession, project_id: UUID, urn: str) -> LineageAnalysisResponse:
		"""
		Diagnoses a specific node by recursively analyzing its upstream dependencies.
		Powered by the ambyte_rules LineageGraph and Recursive CTEs.
		"""
		# 1. Initialize the Rules Engine graph adapter
		provider = PostgresMetadataProvider(db)
		graph = LineageGraph(provider)

		# 2. Execute SQL CTE to find the raw upstream path (Ancestors)
		# This gives us the exact nodes that feed into the requested URN
		ancestors = await provider.get_upstream_ancestors(urn)

		# 3. Calculate Inherited Properties
		# These methods recursively check metadata (tags/policies) across all ancestors
		risk_enum = await graph.get_inherited_risk(urn)
		sensitivity_enum = await graph.get_inherited_sensitivity(urn)

		# 4. Detect Poison Pills
		# Identifies specific upstream raw tables that contain restrictive legal clauses
		poisoned_urns = await graph.get_poisoned_constraints(urn)

		# 5. Format and return
		return LineageAnalysisResponse(
			target_urn=urn,
			inherited_risk=risk_enum.name if hasattr(risk_enum, 'name') else str(risk_enum),
			inherited_sensitivity=sensitivity_enum.name if hasattr(sensitivity_enum, 'name') else str(sensitivity_enum),
			poisoned_constraints=poisoned_urns,
			upstream_path=ancestors,
		)

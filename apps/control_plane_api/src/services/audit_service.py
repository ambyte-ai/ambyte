import logging
import uuid
from uuid import UUID

from ambyte_schemas.models.audit import AuditBlockHeader, AuditLogEntry, AuditProof, Decision, PolicyEvaluationTrace
from ambyte_schemas.models.common import Actor, ActorType
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.hashing import compute_entry_hash
from src.core.merkle import MerkleTree
from src.db.models.audit import AuditLog
from src.schemas.audit import AuditLogCreate
from src.services.audit_buffer import audit_buffer

logger = logging.getLogger(__name__)


class AuditService:
	"""
	Manages the write-path for Audit Logs.
	Supports both:
	  - Direct Postgres writes (used by background consumers)
	  - Redis Stream buffering (used by hot-path endpoints)
	"""  # noqa: E101

	# ==========================================================================
	# Redis Stream Buffer (Fast Path)
	# ==========================================================================
	@staticmethod
	def _map_to_canonical(entry: AuditLogCreate) -> AuditLogEntry:
		"""
		Transforms the simple Ingest DTO into the strict Canonical Domain Model.
		This ensures the Worker receives data that passes strict validation.
		"""
		# 1. Resolve Decision Enum (String -> IntEnum)
		# Handle "ALLOW", "DENY" strings robustly
		try:
			decision_enum = Decision[entry.decision.upper()]
		except KeyError:
			decision_enum = Decision.UNSPECIFIED

		# 2. Map Trace Object
		# API uses ReasonTrace schema, Domain uses PolicyEvaluationTrace schema
		eval_trace = None
		if entry.reason_trace:
			eval_trace = PolicyEvaluationTrace(
				reason_summary=entry.reason_trace.decision_reason,
				contributing_obligation_ids=[p.obligation_id for p in entry.reason_trace.contributing_policies],
				policy_version_hash=entry.reason_trace.resolved_policy_hash or '',
				cache_hit=entry.reason_trace.cache_hit,
			)

		# 3. Construct Canonical Entry
		return AuditLogEntry(
			id=str(uuid.uuid4()),  # Generate ID here so it's consistent
			timestamp=entry.timestamp,
			actor=Actor(
				id=entry.actor_id,
				type=ActorType.UNSPECIFIED,  # We don't know type from simple ingest
				roles=[],
				attributes={},
			),
			resource_urn=entry.resource_urn,
			action=entry.action,
			decision=decision_enum,
			evaluation_trace=eval_trace,
			request_context=entry.request_context or {},
			entry_hash='',  # Calculated by worker
		)

	@staticmethod
	async def log_to_buffer(project_id: UUID, entry: AuditLogCreate) -> str | None:
		"""
		Write a single audit entry to Redis Stream (fast path).
		Sub-millisecond latency, decoupled from database writes.

		Returns:
			The stream entry ID, or None on error.
		"""  # noqa: E101
		return await audit_buffer.push(project_id, entry)

	@staticmethod
	async def log_batch_to_buffer(project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Bulk write audit entries to Redis Stream (fast path).
		Uses pipelining for maximum throughput.

		Returns:
			Number of entries successfully buffered.
		"""  # noqa: E101
		canonical_entries = [AuditService._map_to_canonical(e) for e in entries]

		return await audit_buffer.push_batch(project_id, canonical_entries)

	# ==========================================================================
	# Direct Postgres Writes (Slow Path - for Background Consumers)
	# ==========================================================================

	@staticmethod
	async def log_single(db: AsyncSession, project_id: UUID, entry: AuditLogCreate) -> AuditLog:
		"""
		Write a single audit entry directly to Postgres.
		Used by the Decision Engine synchronously (or via BackgroundTask).
		"""
		# 1. Prepare Data
		# We need the dictionary representation for hashing
		entry_dict = entry.model_dump(mode='json', exclude_none=True)

		# 2. Compute Hash
		entry_hash = compute_entry_hash(entry_dict)

		# 3. Serialize nested fields for DB (JSONB)
		reason_trace_data = entry.reason_trace.model_dump() if entry.reason_trace else None
		db_obj = AuditLog(
			project_id=project_id,
			timestamp=entry.timestamp,
			actor_id=entry.actor_id,
			resource_urn=entry.resource_urn,
			action=entry.action,
			decision=entry.decision,
			reason_trace=reason_trace_data,
			request_context=entry.request_context,
			entry_hash=entry_hash,
		)
		db.add(db_obj)
		await db.commit()
		return db_obj

	@staticmethod
	async def log_batch(db: AsyncSession, project_id: UUID, entries: list[AuditLogCreate]) -> int:
		"""
		Bulk write audit entries directly to Postgres.
		Used by the SDK background sync or bulk ingest endpoint.
		Returns the count of inserted rows.
		"""
		if not entries:
			return 0

		db_objects = []
		for entry in entries:
			# 1. Compute Hash
			entry_dict = entry.model_dump(mode='json', exclude_none=True)
			entry_hash = compute_entry_hash(entry_dict)

			# 2. Create DB Object
			db_objects.append(
				AuditLog(
					project_id=project_id,
					timestamp=entry.timestamp,
					actor_id=entry.actor_id,
					resource_urn=entry.resource_urn,
					action=entry.action,
					decision=entry.decision,
					reason_trace=entry.reason_trace.model_dump() if entry.reason_trace else None,
					request_context=entry.request_context,
					entry_hash=entry_hash,
				)
			)

		# Use bulk save for performance
		db.add_all(db_objects)
		await db.commit()

		count = len(db_objects)
		logger.info(f'Ingested {count} audit logs for project {project_id}')
		return count

	@staticmethod
	async def get_proof(db: AsyncSession, project_id: UUID, log_id: UUID) -> AuditProof:
		"""
		Generates a Cryptographic Inclusion Proof for a specific log entry.

		Steps:
		1. Fetch the Log and its associated Block.
		2. If not sealed (no block), raise 404/409.
		3. Fetch ALL other log hashes in that block.
		4. Reconstruct the Merkle Tree in memory.
		5. Extract the sibling path for the target log.
		6. Return the Proof bundle.
		"""

		# 1. Fetch Log + Block
		stmt = (
			select(AuditLog)
			.where(AuditLog.id == log_id, AuditLog.project_id == project_id)
			.options(selectinload(AuditLog.block))
		)
		result = await db.execute(stmt)
		log_orm = result.scalars().first()

		if not log_orm:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Audit log entry not found.')

		if not log_orm.block:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail='Log entry is currently buffered and has not yet been sealed into a block. Try again later.',
			)

		# 2. Fetch Siblings
		# We need every hash in this block to reconstruct the tree and find the path.
		# Optimization: Only select entry_hash, not full rows.
		siblings_stmt = select(AuditLog.entry_hash).where(AuditLog.block_id == log_orm.block_id)
		siblings_res = await db.execute(siblings_stmt)
		all_leaf_hashes = siblings_res.scalars().all()

		# 3. Build Tree & Get Path
		tree = MerkleTree(leaves=list(all_leaf_hashes))

		# Verification sanity check
		if tree.root != log_orm.block.merkle_root:
			logger.critical(f'INTEGRITY ERROR: Computed Root {tree.root} != Stored Root {log_orm.block.merkle_root}')
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail='System Integrity Error: Recomputed Merkle Root does not match stored Block Header.',
			)

		proof_path = tree.get_proof(log_orm.entry_hash)

		# 4. Map ORM -> Pydantic Response

		# Map Log Entry
		# (Reusing logic from _map_to_canonical conceptually, but mapping from DB model)
		entry_model = AuditLogEntry(
			id=str(log_orm.id),
			timestamp=log_orm.timestamp,
			actor=Actor(id=log_orm.actor_id, type=ActorType.UNSPECIFIED),  # Type often lost in flattening
			resource_urn=log_orm.resource_urn,
			action=log_orm.action,
			decision=Decision[log_orm.decision],
			evaluation_trace=PolicyEvaluationTrace.model_validate(log_orm.reason_trace)
			if log_orm.reason_trace
			else None,
			request_context=log_orm.request_context or {},
			entry_hash=log_orm.entry_hash,
		)

		# Map Block Header
		block_model = AuditBlockHeader(
			id=str(log_orm.block.id),
			sequence_index=log_orm.block.sequence_index,
			prev_block_hash=log_orm.block.prev_block_hash,
			merkle_root=log_orm.block.merkle_root,
			timestamp_start=log_orm.block.timestamp_start,
			timestamp_end=log_orm.block.timestamp_end,
			log_count=log_orm.block.log_count,
			signature=log_orm.block.signature,
		)

		return AuditProof(entry=entry_model, block_header=block_model, merkle_siblings=proof_path)

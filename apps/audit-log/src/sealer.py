import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.config import settings
from src.crypto.merkle import MerkleTree
from src.crypto.signer import AuditSigner
from src.db.models.audit import AuditBlock, AuditLog
from src.repository import AuditRepository

logger = logging.getLogger(__name__)


class SealerService:
	"""
	Background worker that "Seals" audit logs into immutable blocks.

	Workflow:
	1. Scan for distinct Projects that have unsealed logs.
	2. For each project:
	   a. Fetch unsealed logs (ordered by timestamp).
	   b. Check sealing criteria (Count threshold OR Time threshold).
	   c. Build Merkle Tree from log hashes.
	   d. Fetch Previous Block hash (for chaining).
	   e. Construct and Sign the new AuditBlock.
	   f. Commit Block + Update Logs in a single atomic transaction.
	"""  # noqa: E101

	def __init__(self, repository: AuditRepository, redis_client: Redis):
		self.repository = repository
		self.redis = redis_client
		self.signer = AuditSigner()  # Loads key from env/settings
		self._running = False

		# Configuration
		self.seal_interval = 30.0  # Run loop every 30s
		self.min_logs_threshold = settings.SEAL_MIN_LOGS
		self.max_time_window = settings.SEAL_MAX_TIME_WINDOW

		# Genesis Hash (Used for the very first block of a project)
		self.genesis_hash = '0' * 64

	async def start(self):
		"""Main loop entry point."""
		self._running = True
		logger.info('Sealer Service started.')

		while self._running:
			try:
				await self._seal_cycle()
			except Exception as e:
				logger.error(f'Sealer cycle failed: {e}', exc_info=True)

			await asyncio.sleep(self.seal_interval)

	def stop(self):
		self._running = False

	async def _seal_cycle(self):
		"""
		Iterates over all projects with pending data and attempts to seal them.
		"""
		if not self.repository.engine:
			logger.warning('DB not connected, skipping seal cycle.')
			return

		async with self.repository.engine.begin() as conn:
			# 1. Find projects with unsealed logs
			# SELECT DISTINCT project_id FROM audit_logs WHERE block_id IS NULL
			stmt = select(AuditLog.project_id).where(AuditLog.block_id.is_(None)).distinct()
			result = await conn.execute(stmt)
			project_ids = result.scalars().all()

		if not project_ids:
			return

		logger.debug(f'Found {len(project_ids)} projects with unsealed logs.')

		# Process each project independently
		# TODO: In high scale, dispatch these to a task queue or partition via consistent hashing
		for pid in project_ids:
			await self._process_project(pid)

	async def _process_project(self, project_id: UUID):
		"""
		Logic to seal a single project's logs.
		Uses its own transaction to ensure atomicity per block.
		Wraps the entire process in a Redis Distributed Lock to prevent race conditions.
		"""
		lock_key = f'audit:sealer:lock:{project_id}'
		# Acquire lock with a timeout (e.g., 60s) to prevent indefinite holding if crash.
		# blocking=False ensures we skip if another instance is working on it.
		async with self.redis.lock(lock_key, timeout=60, blocking=False) as lock:
			if not await lock.locked():
				logger.debug(f'Project {project_id} is locked by another worker. Skipping.')
				return

			await self._process_project_logic(project_id)

	async def _process_project_logic(self, project_id: UUID):
		"""
		Core logic extracted for cleaner locking wrapper.
		"""
		assert self.repository.engine is not None
		async with self.repository.engine.begin() as conn:
			# 1. Fetch unsealed logs
			# We limit the batch size to avoid memory issues building the tree
			limit = 5000

			stmt = (
				select(AuditLog.id, AuditLog.entry_hash, AuditLog.timestamp)
				.where(AuditLog.project_id == project_id, AuditLog.block_id.is_(None))
				.order_by(AuditLog.timestamp.asc())  # Oldest first
				.limit(limit)
			)

			result = await conn.execute(stmt)
			rows = result.all()

			if not rows:
				return

			# 2. Check Thresholds
			count = len(rows)
			oldest_ts = rows[0].timestamp.replace(tzinfo=timezone.utc)
			now = datetime.now(timezone.utc)
			age_seconds = (now - oldest_ts).total_seconds()

			should_seal = (count >= self.min_logs_threshold) or (age_seconds >= self.max_time_window)

			if not should_seal:
				# Keep buffering
				return

			logger.info(f'Sealing block for Project {project_id} ({count} logs, {int(age_seconds)}s old)')

			# 3. Get Previous Block (The "Chain")
			last_block_stmt = (
				select(AuditBlock.sequence_index, AuditBlock.merkle_root)
				.where(AuditBlock.project_id == project_id)
				.order_by(AuditBlock.sequence_index.desc())
				.limit(1)
			)
			last_block_res = await conn.execute(last_block_stmt)
			last_block_row = last_block_res.first()

			# Determine new block metadata
			if last_block_row:
				new_index = last_block_row.sequence_index + 1
				prev_hash = last_block_row.merkle_root
			else:
				new_index = 0
				prev_hash = self.genesis_hash

			# 4. Build Merkle Tree
			leaf_hashes = [r.entry_hash for r in rows]
			# Ensure hashes are valid (non-empty)
			valid_hashes = [h for h in leaf_hashes if h and len(h) == 64]

			if not valid_hashes:
				logger.error(f'Project {project_id} has unhashed logs. Skipping seal.')
				return

			tree = MerkleTree(valid_hashes)
			merkle_root = tree.get_root()

			# 5. Determine Time Range
			ts_start = rows[0].timestamp
			ts_end = rows[-1].timestamp

			# 6. Create Signature
			# Canonical String for Signing: "INDEX|PREV_HASH|ROOT|COUNT"
			# Simple format, easy to reproduce in verification logic
			sign_payload = f'{new_index}|{prev_hash}|{merkle_root}|{count}'.encode()
			signature = self.signer.sign(sign_payload)

			# 7. Insert Block Header
			# We use returning(AuditBlock.id) to get the ID for the foreign key update
			block_stmt = (
				pg_insert(AuditBlock)
				.values(
					project_id=project_id,
					sequence_index=new_index,
					prev_block_hash=prev_hash,
					merkle_root=merkle_root,
					timestamp_start=ts_start,
					timestamp_end=ts_end,
					log_count=count,
					signature=signature,
				)
				.returning(AuditBlock.id)
			)

			block_res = await conn.execute(block_stmt)
			new_block_id = block_res.scalar_one()

			# 8. Link Logs to Block (The "Seal")
			log_ids = [r.id for r in rows]
			update_stmt = update(AuditLog).where(AuditLog.id.in_(log_ids)).values(block_id=new_block_id)
			await conn.execute(update_stmt)

			# Commit happens automatically via 'async with engine.begin()' context exit
			logger.info(f'✅ Sealed Block #{new_index} for Project {project_id}. Root: {merkle_root[:10]}...')

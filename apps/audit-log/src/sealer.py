import asyncio
import logging
import os
import socket
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

	Architecture: Distributed Leader-Follower
	1. Scheduler Loop (Leader Only):
	   - Scans DB for projects with pending logs.
	   - Pushes project_ids to a Redis Stream Job Queue.
	   - Uses Redis Sets to debounce (ensure a project isn't queued twice).

	2. Worker Loop (All Replicas):
	   - Consumes project_ids from Redis Stream.
	   - Builds Merkle Trees and signs blocks.
	   - Commits to Postgres.
	"""  # noqa: E101

	def __init__(self, repository: AuditRepository, redis_client: Redis):
		self.repository = repository
		self.redis = redis_client
		self.signer = AuditSigner()
		self._running = False

		# Configuration
		self.scheduler_interval = 10.0  # Leader scans DB every 10s
		self.min_logs_threshold = settings.SEAL_MIN_LOGS
		self.max_time_window = settings.SEAL_MAX_TIME_WINDOW

		# Redis Keys
		self.stream_key = 'audit:jobs:seal'
		self.pending_set_key = 'audit:jobs:seal:pending'  # Set of project_ids currently in queue
		self.leader_lock_key = 'audit:sealer:leader'
		self.consumer_group = 'audit_sealer_group'

		# Unique consumer name for this process
		pod_name = os.getenv('HOSTNAME', socket.gethostname())
		pid = os.getpid()
		self.consumer_name = f'sealer-{pod_name}-{pid}'

		# Genesis Hash (Used for the very first block of a project)
		self.genesis_hash = '0' * 64

	async def start(self):
		"""Main entry point. Starts both Scheduler and Worker loops."""
		self._running = True
		logger.info(f'Sealer Service started. Worker ID: {self.consumer_name}')

		# Ensure Consumer Group exists
		try:
			await self.redis.xgroup_create(self.stream_key, self.consumer_group, id='0', mkstream=True)
		except Exception as e:
			if 'BUSYGROUP' not in str(e):
				logger.error(f'Failed to create consumer group: {e}')

		# Run loops concurrently
		await asyncio.gather(self._scheduler_loop(), self._worker_loop(), return_exceptions=True)

	def stop(self):
		self._running = False

	# ==========================================================================
	# 1. Scheduler Loop (Leader Only)
	# ==========================================================================

	async def _scheduler_loop(self):
		"""
		Periodically scans for dirty projects and queues them.
		Only runs if this instance acquires the Leader Lock.
		"""
		logger.info('Scheduler loop started.')

		while self._running:
			try:
				# Attempt Leader Election (15s TTL)
				is_leader = await self.redis.set(self.leader_lock_key, self.consumer_name, nx=True, ex=15)

				if is_leader:
					# Refresh lock expiration if we already own it
					await self.redis.expire(self.leader_lock_key, 15)
					await self._schedule_jobs()
				else:
					# Check if we are the leader (refresh logic)
					current_leader = await self.redis.get(self.leader_lock_key)
					if current_leader and current_leader.decode() == self.consumer_name:
						await self.redis.expire(self.leader_lock_key, 15)
						await self._schedule_jobs()
					# else: I am a follower, do nothing this cycle.

			except Exception as e:
				logger.error(f'Scheduler error: {e}', exc_info=True)

			await asyncio.sleep(self.scheduler_interval)

	async def _schedule_jobs(self):
		"""
		Identifies projects needing attention and pushes them to the Job Queue.
		"""
		if not self.repository.engine:
			return

		# 1. Find dirty projects (projects with unsealed logs)
		# Optimization: This query assumes index on (block_id) where null.
		async with self.repository.engine.begin() as conn:
			stmt = select(AuditLog.project_id).where(AuditLog.block_id.is_(None)).distinct()
			result = await conn.execute(stmt)
			dirty_project_ids = [str(pid) for pid in result.scalars().all()]

		if not dirty_project_ids:
			return

		# 2. Filter out projects already in the queue (Debounce)
		# We use SISMEMBER via pipeline for efficiency
		async with self.redis.pipeline(transaction=False) as pipe:
			for pid in dirty_project_ids:
				pipe.sismember(self.pending_set_key, pid)
			is_pending_results = await pipe.execute()

		projects_to_queue = [
			pid for pid, is_pending in zip(dirty_project_ids, is_pending_results, strict=True) if not is_pending
		]

		if not projects_to_queue:
			return

		# 3. Enqueue Jobs
		# We add to the pending set AND the stream atomically-ish
		async with self.redis.pipeline(transaction=True) as pipe:
			for pid in projects_to_queue:
				# Add to Pending Set (Debounce)
				pipe.sadd(self.pending_set_key, pid)
				# Add to Job Stream
				pipe.xadd(self.stream_key, {'project_id': pid})

			await pipe.execute()

		logger.debug(f'Scheduler queued {len(projects_to_queue)} projects for sealing.')

	# ==========================================================================
	# 2. Worker Loop (All Instances)
	# ==========================================================================

	async def _worker_loop(self):
		"""
		Consumes jobs from the Redis Stream and executes sealing logic.
		"""
		logger.info('Worker loop started.')

		while self._running:
			try:
				# Block for 2 seconds waiting for jobs
				response = await self.redis.xreadgroup(
					self.consumer_group, self.consumer_name, {self.stream_key: '>'}, count=1, block=2000
				)

				if not response:
					continue

				# Parse Job
				stream, messages = response[0]
				for message_id_byte, fields in messages:
					message_id = message_id_byte.decode('utf-8')
					try:
						# Decode Fields
						project_id_str = fields[b'project_id'].decode('utf-8')
						project_id = UUID(project_id_str)

						# Execute Logic
						await self._process_project(project_id)

						# Cleanup & Ack
						async with self.redis.pipeline(transaction=True) as pipe:
							pipe.xack(self.stream_key, self.consumer_group, message_id)
							pipe.srem(self.pending_set_key, project_id_str)
							await pipe.execute()

					except Exception as e:
						logger.error(f'Failed to process job {message_id}: {e}', exc_info=True)
						# Note: We do NOT Ack or Srem here.
						# Redis PEL (Pending Entries List) will retain this message.
						# A separate "Claiming" process (consumer recovery) would be needed for robustness
						# if this worker crashes permanently. For now, it will retry on restart or timeout.

			except Exception as e:
				logger.error(f'Worker loop error: {e}')
				await asyncio.sleep(1)

	# ==========================================================================
	# 3. Core Logic
	# ==========================================================================

	async def _process_project(self, project_id: UUID):
		"""
		Logic to seal a single project's logs.
		Wraps the core logic in a distributed lock for safety,
		even though the queue should prevent concurrency.
		"""
		lock_key = f'audit:sealer:lock:{project_id}'

		# Acquire lock with a timeout (e.g., 60s).
		# We use blocking=False because if it's locked, another worker is handling it
		# (possibly via a race condition or retry), so we can skip.
		async with self.redis.lock(lock_key, timeout=60, blocking=False) as lock:
			if not await lock.locked():
				# Should be rare with the queue system, but good safety net.
				return

			await self._process_project_logic(project_id)

	async def _process_project_logic(self, project_id: UUID):
		"""
		Calculates Merkle Root, Signs Block, and Commits to DB.
		"""
		assert self.repository.engine is not None
		async with self.repository.engine.begin() as conn:
			# 1. Fetch unsealed logs
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
			sign_payload = f'{new_index}|{prev_hash}|{merkle_root}|{count}'.encode()
			signature = self.signer.sign(sign_payload)

			# 7. Insert Block Header
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

			logger.info(f'✅ Sealed Block #{new_index} for Project {project_id}. Root: {merkle_root[:10]}...')

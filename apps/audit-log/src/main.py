import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ambyte_schemas.models.audit import AuditLogEntry
from fastapi import FastAPI
from redis.asyncio import from_url
from src.config import settings
from src.consumer import StreamConsumer
from src.hashing import compute_entry_hash
from src.repository import AuditRepository
from src.sealer import SealerService

# Configure logging
logging.basicConfig(
	level=settings.LOG_LEVEL,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(settings.SERVICE_NAME)


@dataclass
class QueueMessage:
	"""
	Internal message structure passing data from Reader (Redis) to Writer (Postgres).
	"""

	stream_key: str
	message_id: str
	db_row: dict[str, Any]


# ==============================================================================
# Global Components
# ==============================================================================
redis_client = from_url(settings.REDIS_URL, encoding='utf-8', decode_responses=False)
consumer = StreamConsumer(redis_client)
repository = AuditRepository()
sealer = SealerService(repository, redis_client)

# If Postgres slows down, the queue fills, blocking the Reader,
# which stops consuming from Redis until space is available.
audit_queue: asyncio.Queue[QueueMessage] = asyncio.Queue(maxsize=10000)


# ==============================================================================
# 1. Reader Task (Producer)
# ==============================================================================
async def consume_from_redis():
	"""
	High-throughput Reader.
	1. Reads from Redis Stream.
	2. Performs CPU-bound work (Parsing, Canonicalization, Hashing).
	3. Pushes to internal Queue.
	"""
	logger.info('Starting Redis Consumer (Producer Task)...')
	async for stream_key, msg_id, raw_payload in consumer.consume():
		try:
			# 1. Extract Project ID from stream key (audit:logs:UUID)
			project_id = stream_key.split(':')[-1]

			# 2. Rehydrate Pydantic Model (Validation)
			entry_dict = raw_payload.get('data')
			if not entry_dict:
				if isinstance(raw_payload, dict):
					entry_dict = raw_payload
				else:
					logger.error(f'Invalid payload format in {stream_key}')
					continue

			# 3. Compute Cryptographic Hash (The "Leaf")
			log_entry = AuditLogEntry.model_validate(entry_dict)

			# Generate hash from the clean model dump
			canonical_dict = log_entry.model_dump(mode='json', exclude={'entry_hash'})
			entry_hash = compute_entry_hash(canonical_dict)

			# Assign hash to object
			log_entry.entry_hash = entry_hash

			# 4. Transform to DB Row
			row = repository.map_to_db_row(project_id, log_entry)

			# 5. Enqueue (Blocks if queue is full -> Backpressure)
			await audit_queue.put(QueueMessage(stream_key, msg_id, row))

		except Exception as e:
			logger.error(f'Failed to process message {msg_id}: {e}', exc_info=True)
			# We don't ACK failed messages so they can be retried or DLQ'd via Redis tools
			continue


# ==============================================================================
# 2. Writer Task (Consumer)
# ==============================================================================
async def writer_worker():
	"""
	Batched Writer.
	1. Reads from internal Queue.
	2. Aggregates messages based on Count (BATCH_SIZE) or Time (FLUSH_INTERVAL).
	3. Bulk Inserts to Postgres.
	4. ACKs to Redis.
	"""
	logger.info('Starting DB Writer (Consumer Task)...')
	loop = asyncio.get_running_loop()

	while True:
		batch: list[QueueMessage] = []

		try:
			# --- A. Smart Batching Logic ---

			# 1. Blocking Wait: Don't spin CPU if queue is empty. Wait for first item.
			item = await audit_queue.get()
			batch.append(item)

			# 2. Deadline Collection: Try to fill batch until timeout
			deadline = loop.time() + settings.BATCH_FLUSH_INTERVAL

			while len(batch) < settings.BATCH_SIZE:
				timeout = deadline - loop.time()
				if timeout <= 0:
					break

				try:
					# Fetch next item with timeout
					item = await asyncio.wait_for(audit_queue.get(), timeout=timeout)
					batch.append(item)
				except asyncio.TimeoutError:
					break  # Timeout reached, flush what we have

			# --- B. Flush Logic ---

			if batch:
				rows = [m.db_row for m in batch]

				# 1. DB Commit
				await repository.insert_batch(rows)

				# 2. Redis ACK (Grouped by stream)
				acks: dict[str, list[str]] = {}
				for m in batch:
					if m.stream_key not in acks:
						acks[m.stream_key] = []
					acks[m.stream_key].append(m.message_id)

				for stream, ids in acks.items():
					await consumer.ack(stream, ids)

				# 3. Mark tasks as done in queue
				for _ in batch:
					audit_queue.task_done()

		except asyncio.CancelledError:
			# Graceful shutdown signal
			break
		except Exception as e:
			# We crash the process. Kubernetes/Docker will restart it.
			# Redis consumer group offset remains un-acked, so messages are redelivered.
			logger.critical(f'FATAL: DB Flush failed. Crashing worker to trigger redelivery. Error: {e}')
			sys.exit(1)


# ==============================================================================
# Application Lifecycle
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
	# Startup
	logger.info('Audit Worker starting up...')
	await repository.connect()

	# Start Producer/Consumer Tasks
	producer_task = asyncio.create_task(consume_from_redis())
	consumer_task = asyncio.create_task(writer_worker())

	# Start the Sealer (Runs independently)
	sealer_task = asyncio.create_task(sealer.start())

	yield

	# Shutdown
	logger.info('Audit Worker shutting down...')
	consumer.stop()
	sealer.stop()

	# 1. Stop Producer (Stop reading new data)
	producer_task.cancel()
	try:
		await producer_task
	except asyncio.CancelledError:
		pass

	# 2. Wait for Queue to drain (Best effort flush)
	# We give the writer a few seconds to flush remaining items in memory
	if not audit_queue.empty():
		logger.info(f'Draining {audit_queue.qsize()} items from queue...')
		try:
			# Wait for queue to be empty (all items processed & task_done called)
			await asyncio.wait_for(audit_queue.join(), timeout=5.0)
		except asyncio.TimeoutError:
			logger.warning('Timed out waiting for queue to drain. Some buffered logs may be re-processed on restart.')

	# 3. Stop Consumer
	consumer_task.cancel()
	try:
		await consumer_task
	except asyncio.CancelledError:
		pass

	# 4. Stop Sealer
	sealer_task.cancel()
	try:
		await sealer_task
	except asyncio.CancelledError:
		pass

	await redis_client.aclose()
	await repository.close()


app = FastAPI(title='Ambyte Audit Worker', lifespan=lifespan)


@app.get('/health')
def health_check():
	# Deep check: Ensure DB engine is up
	if repository.engine is None:
		return {'status': 'error', 'detail': 'DB not connected'}
	return {'status': 'ok', 'service': settings.SERVICE_NAME, 'queue_size': audit_queue.qsize()}


if __name__ == '__main__':
	import uvicorn

	uvicorn.run(app, host=settings.HOST, port=settings.PORT)

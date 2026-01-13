import asyncio
import logging
from contextlib import asynccontextmanager

from ambyte_schemas.models.audit import AuditLogEntry
from fastapi import FastAPI
from redis.asyncio import from_url
from src.config import settings
from src.consumer import StreamConsumer
from src.hashing import compute_entry_hash
from src.repository import AuditRepository

# Configure logging
logging.basicConfig(
	level=settings.LOG_LEVEL,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(settings.SERVICE_NAME)

# ==============================================================================
# Global Components
# ==============================================================================
redis_client = from_url(settings.REDIS_URL, encoding='utf-8', decode_responses=False)
consumer = StreamConsumer(redis_client)
repository = AuditRepository()

pending_acks: dict[str, list[str]] = {}


# ==============================================================================
# Worker Logic
# ==============================================================================
async def process_message_batch():
	"""
	The core loop: Read -> Hash -> Buffer -> Flush -> Ack
	"""
	async for stream_key, msg_id, raw_payload in consumer.consume():
		try:
			# 1. Extract Project ID from stream key (audit:logs:UUID)
			project_id = stream_key.split(':')[-1]

			# 2. Rehydrate Pydantic Model (Validation)
			entry_dict = raw_payload.get('data')
			if not entry_dict:
				# Should already be parsed by consumer, but double check type
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

			# 4. Add to Persistence Buffer
			repository.add(project_id, log_entry)

			# Track for ACK
			if stream_key not in pending_acks:
				pending_acks[stream_key] = []
			pending_acks[stream_key].append(msg_id)

			# 5. Flush if Buffer Full
			if repository.buffer_size >= settings.BATCH_SIZE:
				await _flush_and_ack()

		except Exception as e:
			logger.error(f'Failed to process message {msg_id}: {e}', exc_info=True)
			# We don't ACK failed messages so they can be retried or DLQ'd
			continue

	# End of loop (shouldn't happen unless stopped)


async def _flush_and_ack():
	"""Helper to commit to DB and then ACK in Redis."""
	if repository.buffer_size == 0:
		return

	try:
		# 1. DB Commit
		await repository.flush()

		# 2. Redis ACK
		acks_to_send = {k: list(v) for k, v in pending_acks.items() if v}

		# Reset
		pending_acks.clear()

		for stream, ids in acks_to_send.items():
			if ids:
				await consumer.ack(stream, ids)

	except Exception as e:
		logger.critical(f'Flush failed! Data remains in Redis (will retry): {e}')
		# We assume the repository kept the buffer or raised. TODO: Check if this is true
		# Since we didn't ACK, Redis will redeliver these on restart.


async def periodic_flush_task():
	"""
	Background timer to flush buffer if it hasn't filled up.
	This ensures low-volume logs don't get stuck in memory.
	"""
	# TODO: A more complex implementation would use a Queue between consumer and writer.
	while True:
		await asyncio.sleep(settings.BATCH_FLUSH_INTERVAL)
		if repository.buffer_size > 0:
			logger.debug(f'Time-based flush triggered for {repository.buffer_size} items.')
			await _flush_and_ack()


# ==============================================================================
# Application Lifecycle
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
	# Startup
	logger.info('Audit Worker starting up...')
	await repository.connect()

	# Run worker loops as background tasks
	consumer_task = asyncio.create_task(process_message_batch())
	flush_task = asyncio.create_task(periodic_flush_task())

	yield

	# Shutdown
	logger.info('Audit Worker shutting down...')
	consumer.stop()

	# Wait briefly for tasks to finish
	await asyncio.sleep(0.5)
	consumer_task.cancel()
	flush_task.cancel()

	try:
		await consumer_task
	except asyncio.CancelledError:
		pass

	try:
		await flush_task
	except asyncio.CancelledError:
		pass

	await redis_client.aclose()
	await repository.close()


app = FastAPI(title='Ambyte Audit Worker', lifespan=lifespan)


@app.get('/health')
def health_check():
	return {'status': 'ok', 'service': settings.SERVICE_NAME}


if __name__ == '__main__':
	import uvicorn

	# Run the FastAPI app which starts the worker loop in lifespan
	uvicorn.run(app, host=settings.HOST, port=settings.PORT)

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from redis.asyncio import Redis
from src.config import settings

logger = logging.getLogger(__name__)


class StreamConsumer:
	"""
	Manages Redis Stream consumption across multiple dynamic project streams.

	Features:
	- Auto-discovery of new tenant streams (audit:logs:*).
	- Consumer Group coordination (XREADGROUP).
	- Yields raw messages to the main loop for processing.
	"""

	def __init__(self, redis: Redis):
		self.redis = redis
		self.known_streams: set[str] = set()
		self.group_name = settings.CONSUMER_GROUP_NAME
		self.consumer_name = settings.CONSUMER_NAME
		self._running = False

	async def start_discovery(self):
		"""
		Background task: Periodically SCAN for new project streams.
		Redis Streams are created lazily by the API, so we must watch for them.
		"""
		logger.info('Starting stream discovery loop...')
		while self._running:
			try:
				# SCAN is safe for production (doesn't block like KEYS)
				cursor = 0
				new_streams = set()
				while True:
					cursor, keys = await self.redis.scan(cursor, match='audit:logs:*', count=100)
					new_streams.update(k.decode('utf-8') for k in keys)
					if cursor == 0:
						break

				# If we found new streams, initialize Consumer Groups for them
				diff = new_streams - self.known_streams
				if diff:
					logger.info(f'Discovered {len(diff)} new audit streams: {diff}')
					await self._init_groups(list(diff))
					self.known_streams.update(diff)

			except Exception as e:
				logger.error(f'Stream discovery failed: {e}')

			# Sleep before next scan
			await asyncio.sleep(settings.STREAM_DISCOVERY_INTERVAL)

	async def _init_groups(self, streams: list[str]):
		"""
		Ensures the Consumer Group exists for every stream.
		XGROUP CREATE is idempotent with MKSTREAM, but raises BusyGroupError if exists.
		"""
		for stream in streams:
			try:
				# '$' means start consuming only new messages from now on.
				# '0' would mean reprocess everything from the beginning of time.
				# In a real event sourcing system, '0' might be preferred on fresh deploy,
				# but '$' is safer for typical queue behavior. TODO
				await self.redis.xgroup_create(stream, self.group_name, id='0', mkstream=True)
			except Exception as e:
				# "BUSYGROUP Consumer Group name already exists" is expected
				if 'BUSYGROUP' not in str(e):
					logger.error(f'Failed to create group for {stream}: {e}')

	async def consume(self) -> AsyncGenerator[tuple[str, str, dict[str, Any]], None]:
		"""
		Main Loop: Reads from all known streams using Consumer Groups.
		Yields: (stream_key, message_id, payload_dict)
		"""
		self._running = True
		# Start the discovery task in the background
		asyncio.create_task(self.start_discovery())

		logger.info(f"Worker '{self.consumer_name}' started consuming.")

		while self._running:
			if not self.known_streams:
				await asyncio.sleep(1)
				continue

			try:
				# Construct the streams dict for XREADGROUP
				# Format: {stream_key: ">"} where ">" means "give me new messages"
				streams_dict: dict[Any, Any] = dict.fromkeys(self.known_streams, '>')

				# Block for 1 second max if no data
				response = await self.redis.xreadgroup(
					self.group_name,
					self.consumer_name,
					streams_dict,
					count=settings.BATCH_SIZE,
					block=1000,
				)

				# Response structure: [[stream_name, [(id, fields), ...]], ...]
				for stream_byte, messages in response:
					stream_key = stream_byte.decode('utf-8')

					for message_id_byte, fields in messages:
						message_id = message_id_byte.decode('utf-8')

						# Fields are bytes in Redis, decode them
						# The API puts data in the 'data' field as a JSON string
						try:
							raw_json = fields[b'data'].decode('utf-8')
							payload = json.loads(raw_json)
							yield stream_key, message_id, payload
						except (KeyError, json.JSONDecodeError) as e:
							logger.error(f'Corrupt message in {stream_key}: {e}')
							# Ack it anyway to remove poison message
							await self.redis.xack(stream_key, self.group_name, message_id)

			except Exception as e:
				logger.error(f'Consumption error: {e}')
				await asyncio.sleep(1)  # Backoff

	async def ack(self, stream: str, message_ids: list[str]):
		"""
		Acknowledge processed messages so other consumers don't see them.
		"""
		if message_ids:
			await self.redis.xack(stream, self.group_name, *message_ids)

	def stop(self):
		self._running = False

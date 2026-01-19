import logging
import time
from typing import Annotated

import typer
from databricks.sdk.core import DatabricksError

from .config import settings
from .crawler import UnityCatalogCrawler
from .mapper import ResourceMapper
from .sink import AmbyteSink

# Configure a basic logger for the CLI output
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	datefmt='%H:%M:%S',
)
logger = logging.getLogger('ambyte.connector.databricks')

app = typer.Typer(
	name='ambyte-databricks',
	help='Ambyte Databricks Unity Catalog Connector',
	no_args_is_help=True,
)

BATCH_SIZE = 50


@app.command()
def sync_inventory(
	dry_run: Annotated[
		bool, typer.Option('--dry-run', help='Scan and print resources without sending to Ambyte.')
	] = False,
	verbose: Annotated[bool, typer.Option('--verbose', help='Enable debug logging.')] = False,
):
	"""
	Crawls Unity Catalog and pushes table metadata to the Ambyte Control Plane.
	"""
	# 1. Configure Logging
	if verbose:
		logging.getLogger('ambyte').setLevel(logging.DEBUG)
		logger.debug('Debug logging enabled.')

	logger.info(f'Starting Inventory Sync (Dry Run: {dry_run})')

	start_time = time.time()
	total_scanned = 0
	total_synced = 0
	buffer = []

	# 2. Initialize Components
	try:
		# Authenticate with Databricks
		# The settings object handles retrieving credentials from env vars
		db_client = settings.get_databricks_client()

		crawler = UnityCatalogCrawler(db_client)
		mapper = ResourceMapper()

		# Only init sink if we intend to write data
		sink = AmbyteSink() if not dry_run else None

	except Exception as e:
		logger.critical(f'Initialization failed: {e}')
		raise typer.Exit(1) from e

	try:
		# 3. Traversal Loop
		# The crawler yields assets lazily
		for asset in crawler.crawl():
			try:
				# Map internal Databricks format to Ambyte canonical format
				resource = mapper.map(asset)
				buffer.append(resource)
				total_scanned += 1

				# Flush buffer if full
				if len(buffer) >= BATCH_SIZE:
					if not dry_run and sink:
						sink.push_batch(buffer)
						total_synced += len(buffer)
					else:
						logger.info(f'[Dry Run] Would sync batch of {len(buffer)} items.')
						for r in buffer:
							logger.debug(f'  - {r.urn}')

					# Clear buffer
					buffer.clear()

			except Exception as e:
				# Individual mapping failures shouldn't crash the whole sync
				logger.error(f'Failed to process table {asset.table_info.name}: {e}')
				continue

		# 4. Final Flush
		if buffer:
			if not dry_run and sink:
				sink.push_batch(buffer)
				total_synced += len(buffer)
			else:
				logger.info(f'[Dry Run] Would sync final batch of {len(buffer)} items.')

	except KeyboardInterrupt:
		logger.warning('Sync interrupted by user.')
	except DatabricksError as e:
		logger.error(f'Databricks API Error: {e}')
	except Exception as e:
		logger.critical(f'Unexpected fatal error: {e}', exc_info=True)
		raise typer.Exit(1) from e
	finally:
		if sink:
			sink.close()

	# 5. Summary
	duration = time.time() - start_time
	logger.info('=' * 40)
	logger.info('SYNC COMPLETE')
	logger.info(f'Duration:      {duration:.2f}s')
	logger.info(f'Total Scanned: {total_scanned}')
	if not dry_run:
		logger.info(f'Total Synced:  {total_synced}')
	else:
		logger.info('Total Synced:  0 (Dry Run)')
	logger.info('=' * 40)


if __name__ == '__main__':
	app()

import logging
import time
from pathlib import Path
from typing import Annotated

import typer
import yaml
from ambyte_schemas.models.artifact import PolicyBundle
from ambyte_schemas.models.inventory import ResourceCreate
from databricks.sdk.core import DatabricksError

from ambyte_databricks.config import settings
from ambyte_databricks.crawler import UnityCatalogCrawler
from ambyte_databricks.enforcer import PolicyEnforcer
from ambyte_databricks.executor import SqlExecutor
from ambyte_databricks.lineage import LineageExtractor
from ambyte_databricks.mapper import ResourceMapper
from ambyte_databricks.sink import AmbyteSink, ConsoleSink, LocalFileSink, SinkProtocol
from ambyte_databricks.state import GovernanceState

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

inventory_app = typer.Typer(help='Manage metadata and resource inventory.')
app.add_typer(inventory_app, name='inventory')

policy_app = typer.Typer(help='Enforce governance policies.')
app.add_typer(policy_app, name='policy')

lineage_app = typer.Typer(help='Extract and sync data lineage.')
app.add_typer(lineage_app, name='lineage')

BATCH_SIZE = 50


@inventory_app.command(name='sync')
def sync_inventory(
	dry_run: Annotated[
		bool, typer.Option('--dry-run', help='Scan and print resources without sending to Ambyte.')
	] = False,
	output: Annotated[str, typer.Option('--output', '-o', help='Output file path for local mode.')] = 'resources.yaml',
	local: Annotated[
		bool, typer.Option('--local', help='Write inventory to a local file instead of the Control Plane.')
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

		# Select the correct sink strategy based on mode
		if dry_run:
			sink = ConsoleSink()
		elif local:
			sink = LocalFileSink(output_path=output)
		else:
			sink = AmbyteSink()

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
					sink.push_batch(buffer)
					total_synced += len(buffer)

					# Clear buffer
					buffer.clear()

			except Exception as e:
				# Individual mapping failures shouldn't crash the whole sync
				logger.error(f'Failed to process table {asset.table_info.name}: {e}')
				continue

		# 4. Final Flush
		if buffer:
			sink.push_batch(buffer)
			total_synced += len(buffer)

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
	logger.info(f'Duration:	  {duration:.2f}s')
	logger.info(f'Total Scanned: {total_scanned}')
	if not dry_run:
		logger.info(f'Total Synced:  {total_synced}')
	else:
		logger.info('Total Synced:  0 (Dry Run)')
	logger.info('=' * 40)


@policy_app.command(name='enforce')
def enforce_policies(
	bundle_path: Annotated[
		str, typer.Option('--bundle', help='Path to the compiled local_policies.json.')
	] = '.ambyte/dist/local_policies.json',
	inventory_path: Annotated[
		str, typer.Option('--inventory', help='Path to the resources.yaml inventory file.')
	] = 'resources.yaml',
	warehouse_id: Annotated[
		str | None, typer.Option('--warehouse-id', help='Override SQL Warehouse ID from env vars.')
	] = None,
	dry_run: Annotated[bool, typer.Option('--dry-run', help='Generate SQL plan without executing.')] = False,
	verbose: Annotated[bool, typer.Option('--verbose', help='Enable debug logging.')] = False,
):
	"""
	Applies compiled policies to Databricks Unity Catalog.
	Creates Row Filters and Column Masks as SQL UDFs and binds them to tables.
	"""
	if verbose:
		logging.getLogger('ambyte').setLevel(logging.DEBUG)
		logger.debug('Debug logging enabled.')

	# 1. Load Artifacts
	logger.info('Loading policy artifacts...')

	try:
		# Load Policy Bundle
		b_path = Path(bundle_path)
		if not b_path.exists():
			logger.critical(f"Policy bundle not found at {b_path}. Run 'ambyte build' first.")
			raise typer.Exit(1)

		with open(b_path, encoding='utf-8') as f:
			bundle_json = f.read()
		bundle = PolicyBundle.model_validate_json(bundle_json)
		logger.info(f'Loaded bundle v{bundle.schema_version} ({len(bundle.policies)} policies)')

		# Load Inventory
		# Note: resources.yaml structure is {"resources": [...]}
		i_path = Path(inventory_path)
		if not i_path.exists():
			logger.critical(f"Inventory not found at {i_path}. Run 'ambyte-databricks inventory sync' first.")
			raise typer.Exit(1)

		with open(i_path, encoding='utf-8') as f:
			inv_data = yaml.safe_load(f) or {}

		# Parse list of dicts back into ResourceCreate objects
		raw_resources = inv_data.get('resources', [])
		inventory = [ResourceCreate(**r) for r in raw_resources]
		logger.info(f'Loaded {len(inventory)} resources from inventory.')

	except Exception as e:
		logger.critical(f'Failed to load artifacts: {e}')
		raise typer.Exit(1) from e

	# 2. Initialize Infrastructure
	if warehouse_id:
		settings.WAREHOUSE_ID = warehouse_id

	if not settings.WAREHOUSE_ID and not dry_run:
		logger.critical(
			'Warehouse ID is required for enforcement. Set AMBYTE_DATABRICKS_WAREHOUSE_ID or use --warehouse-id.'
		)
		raise typer.Exit(1)

	try:
		client = settings.get_databricks_client()

		# Executor handles SQL submission
		executor = SqlExecutor(client)

		# State manager fetches current UDFs
		state_manager = GovernanceState(client)

		enforcer = PolicyEnforcer(executor, state_manager)

		# 3. Execute
		enforcer.enforce(bundle, inventory, dry_run=dry_run)

		logger.info('Enforcement cycle complete.')

	except Exception as e:
		logger.critical(f'Enforcement failed: {e}', exc_info=verbose)
		raise typer.Exit(1) from e


@lineage_app.command(name='sync')
def sync_lineage(
	lookback_hours: Annotated[int, typer.Option(help='Hours of history to fetch from system tables.')] = 24,
	warehouse_id: Annotated[str | None, typer.Option('--warehouse-id', help='Override SQL Warehouse ID.')] = None,
	dry_run: Annotated[bool, typer.Option('--dry-run', help='Fetch lineage but do not push to Ambyte.')] = False,
	verbose: Annotated[bool, typer.Option('--verbose', help='Enable debug logging.')] = False,
):
	"""
	Crawls 'system.access.table_lineage' and pushes graph edges to Ambyte.
	"""
	if verbose:
		logging.getLogger('ambyte').setLevel(logging.DEBUG)
		logger.debug('Debug logging enabled.')

	# 1. Config Check
	if warehouse_id:
		settings.WAREHOUSE_ID = warehouse_id

	if not settings.WAREHOUSE_ID:
		logger.critical('Warehouse ID is required to query system tables. Set AMBYTE_DATABRICKS_WAREHOUSE_ID.')
		raise typer.Exit(1)

	logger.info(f'Starting Lineage Sync (Lookback: {lookback_hours}h, Dry Run: {dry_run})')

	sink: SinkProtocol | None = None

	try:
		# 2. Initialize
		db_client = settings.get_databricks_client()
		extractor = LineageExtractor(db_client)

		if dry_run:
			sink = ConsoleSink()
		else:
			sink = AmbyteSink()

		total_runs = 0

		# 3. Extract & Push
		for run, event in extractor.extract(lookback_hours=lookback_hours):
			if sink:
				sink.push_lineage(run, event)

			total_runs += 1
			if total_runs % 100 == 0:
				logger.info(f'Processed {total_runs} lineage events...')

		logger.info(f'Lineage sync complete. Total events: {total_runs}')

	except Exception as e:
		logger.critical(f'Lineage sync failed: {e}', exc_info=verbose)
		raise typer.Exit(1) from e
	finally:
		if sink:
			sink.close()


if __name__ == '__main__':
	app()

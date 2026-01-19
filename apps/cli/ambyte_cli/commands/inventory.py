"""
Commands for managing Data Resource Inventory.
"""

from typing import Annotated

import typer
from ambyte_cli.config import get_workspace_root, load_config
from ambyte_cli.services.api_client import CloudApiClient
from ambyte_cli.services.inventory import InventoryLoader
from ambyte_cli.ui.console import console
from rich.table import Table

app = typer.Typer(help='Manage data resources and inventory tags.')


@app.command(name='sync')
def sync_inventory(
	dry_run: Annotated[bool, typer.Option('--dry-run', help='Preview changes without pushing.')] = False,
):
	"""
	Push local resources.yaml to the Control Plane.
	This applies Tags and Metadata required for Policy Matching.
	"""
	config = load_config()
	root = get_workspace_root()

	# 1. Load Local State
	loader = InventoryLoader(root)
	local_resources = loader.load()

	if not local_resources:
		console.print('[yellow]No resources found in resources.yaml[/yellow]')
		return

	# 2. Convert to API payload format
	payload = []
	for r in local_resources:
		# MAP LOCAL YAML -> API SCHEMA
		item = {
			'urn': r.urn,
			'platform': r.platform,
			'name': r.description,  # Map description to name for UI
			'attributes': {
				'tags': r.tags,
				# Merge any other config into attributes
				**r.config,
			},
		}
		payload.append(item)

	console.print(f'[info]Found {len(payload)} resources in local inventory.[/info]')

	if dry_run:
		_print_preview(payload)
		return

	# 3. Push to Cloud
	client = CloudApiClient(config)
	try:
		with console.status('[bold green]Syncing inventory to Control Plane...[/bold green]'):
			# We map the local Pydantic models to the dict structure the API client expects
			upserted = client.sync_inventory(payload)

		console.print(f'[good]✔ Successfully synced {len(upserted)} resources.[/good]')

	except Exception as e:
		console.print(f'[error]Failed to sync inventory:[/error] {e}')
		raise typer.Exit(1) from e


def _print_preview(resources: list[dict]):
	table = Table(title='Inventory Sync Preview (Dry Run)')
	table.add_column('URN', style='cyan')
	table.add_column('Platform')
	table.add_column('Tags', style='magenta')

	for r in resources:
		tags_str = ', '.join(f'{k}={v}' for k, v in r.get('tags', {}).items())
		table.add_row(r['urn'], r['platform'], tags_str)

	console.print(table)

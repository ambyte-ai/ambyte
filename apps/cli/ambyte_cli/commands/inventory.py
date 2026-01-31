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


# Platform color mapping for visual distinction
PLATFORM_STYLES = {
	'snowflake': 'bold cyan',
	'databricks': 'bold red',
	'aws-s3': 'bold yellow',
	's3': 'bold yellow',
	'bigquery': 'bold blue',
	'postgres': 'bold green',
	'postgresql': 'bold green',
	'mysql': 'bold magenta',
	'redshift': 'bold red',
	'local': 'dim',
}


def _get_platform_style(platform: str) -> str:
	"""Get the Rich style for a given platform."""
	return PLATFORM_STYLES.get(platform.lower(), 'white')


def _format_tags(attributes: dict) -> str:
	"""Format tags from attributes for display."""
	tags = attributes.get('tags', {}) if attributes else {}
	if not tags:
		return '[dim]—[/dim]'
	# Show up to 3 tags inline, add ellipsis if more
	items = list(tags.items())[:3]
	formatted = ', '.join(f'[magenta]{k}[/magenta]=[cyan]{v}[/cyan]' for k, v in items)
	if len(tags) > 3:
		formatted += f' [dim](+{len(tags) - 3} more)[/dim]'
	return formatted


def _truncate(text: str, max_len: int) -> str:
	"""Truncate text with ellipsis if too long."""
	if len(text) <= max_len:
		return text
	return text[: max_len - 1] + '…'


@app.command(name='list')
def list_inventory(
	page: Annotated[int, typer.Option('--page', '-p', help='Page number (starts at 1).')] = 1,
	size: Annotated[int, typer.Option('--size', '-s', help='Items per page (max 100).')] = 20,
	platform: Annotated[
		str | None, typer.Option('--platform', '-P', help='Filter by platform (e.g. snowflake, databricks).')
	] = None,
	urn_filter: Annotated[str | None, typer.Option('--urn', '-u', help='Filter by URN (substring match).')] = None,
	output_json: Annotated[bool, typer.Option('--json', '-j', help='Output as JSON instead of table.')] = False,
	show_all: Annotated[
		bool, typer.Option('--all', '-a', help='Fetch all pages (may be slow for large inventories).')
	] = False,
	compact: Annotated[bool, typer.Option('--compact', '-c', help='Compact table view without tags.')] = False,
):
	"""
	List resources from the Control Plane inventory.

	Shows registered data assets with their URN, platform, and metadata tags.
	Supports pagination, filtering, and multiple output formats.

	\b
	Examples:
		ambyte inventory list
		ambyte inventory list --page 2
		ambyte inventory list --platform snowflake
		ambyte inventory list --urn sales
		ambyte inventory list --all --json
	"""
	import json as json_module

	config = load_config()
	client = CloudApiClient(config)

	try:
		if show_all:
			# Fetch all pages
			all_items: list[dict] = []
			current_page = 1
			total_pages = 1

			with console.status('[bold green]Fetching all inventory pages...[/bold green]') as status:
				while current_page <= total_pages:
					status.update(f'[bold green]Fetching page {current_page}...[/bold green]')
					data = client.list_inventory(
						page=current_page,
						size=100,  # Max size for efficiency
						platform=platform,
						urn_filter=urn_filter,
					)
					all_items.extend(data.get('items', []))
					total_pages = data.get('pages', 1)
					current_page += 1

			if output_json:
				console.print(json_module.dumps(all_items, indent=2))
			else:
				_print_inventory_table(all_items, total=len(all_items), page=1, pages=1, compact=compact)
				console.print(f'\n[info]Total: {len(all_items)} resources[/info]')
		else:
			# Single page fetch
			with console.status('[bold green]Fetching inventory...[/bold green]'):
				data = client.list_inventory(
					page=page,
					size=size,
					platform=platform,
					urn_filter=urn_filter,
				)

			items = data.get('items', [])
			total = data.get('total', 0)
			pages = data.get('pages', 1)
			current = data.get('page', page)

			if output_json:
				console.print(json_module.dumps(data, indent=2))
			elif not items:
				console.print('[yellow]No resources found.[/yellow]')
				if platform or urn_filter:
					console.print('[dim]Try adjusting your filters or removing --platform/--urn flags.[/dim]')
			else:
				_print_inventory_table(items, total=total, page=current, pages=pages, compact=compact)
				_print_pagination_footer(current, pages, total, size)

	except Exception as e:
		console.print(f'[error]Failed to list inventory:[/error] {e}')
		raise typer.Exit(1) from e
	finally:
		client.close()


def _print_inventory_table(items: list[dict], total: int, page: int, pages: int, compact: bool = False):
	"""Render a beautiful table of inventory resources."""
	from rich.box import ROUNDED

	# Build title with context
	title = '📦 Inventory Resources'

	table = Table(title=title, box=ROUNDED, show_lines=not compact, header_style='bold white on dark_blue')
	table.add_column('#', style='dim', width=4, justify='right')
	table.add_column('URN', style='cyan', min_width=30, max_width=60, overflow='fold')
	table.add_column('Platform', justify='center', width=12)
	table.add_column('Name', style='white', min_width=15, max_width=30)

	if not compact:
		table.add_column('Tags', min_width=20, max_width=40)

	for idx, resource in enumerate(items, start=1):
		urn = resource.get('urn', '—')
		platform = resource.get('platform', '—')
		name = resource.get('name') or '[dim]—[/dim]'
		attributes = resource.get('attributes', {})

		# Style the platform with color
		platform_styled = f'[{_get_platform_style(platform)}]{platform}[/{_get_platform_style(platform)}]'

		if compact:
			table.add_row(str(idx), urn, platform_styled, _truncate(name, 30))
		else:
			tags_display = _format_tags(attributes)
			table.add_row(str(idx), urn, platform_styled, _truncate(name, 30), tags_display)

	console.print(table)


def _print_pagination_footer(current_page: int, total_pages: int, total_items: int, page_size: int):
	"""Print a helpful pagination footer with navigation hints."""
	from rich.text import Text

	start_item = (current_page - 1) * page_size + 1
	end_item = min(current_page * page_size, total_items)

	# Build navigation hints
	nav_parts = []
	if current_page > 1:
		nav_parts.append(f'[cyan]◀ --page {current_page - 1}[/cyan]')
	if current_page < total_pages:
		nav_parts.append(f'[cyan]--page {current_page + 1} ▶[/cyan]')

	nav_text = '   '.join(nav_parts) if nav_parts else '[dim]Single page[/dim]'

	footer = Text()
	footer.append(f'Showing {start_item}-{end_item} of {total_items}', style='dim')
	footer.append(' │ ', style='dim')
	footer.append(f'Page {current_page}/{total_pages}', style='bold')

	console.print()
	console.print(f'  {footer}   {nav_text}')

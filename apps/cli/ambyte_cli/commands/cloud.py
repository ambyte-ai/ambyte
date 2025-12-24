"""
CLI Commands for interacting with the Ambyte Cloud / Control Plane.
"""

import os
import platform
from pathlib import Path
from typing import Annotated

import httpx
import typer
from ambyte_cli.config import get_workspace_root, load_config, save_config
from ambyte_cli.services.api_client import CloudApiClient
from ambyte_cli.services.auth import CredentialsManager
from ambyte_cli.services.loader import ObligationLoader
from ambyte_cli.services.oidc import OidcService
from ambyte_cli.ui.console import console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

# ==============================================================================
# HELPERS
# ==============================================================================


def _fetch_identity(api_url: str, token: str) -> dict:
	"""
	Calls /v1/auth/whoami to verify the token and get projects.
	"""
	headers = {'Authorization': f'Bearer {token}'}
	try:
		with httpx.Client(timeout=10.0) as client:
			resp = client.get(f'{api_url.rstrip("/")}/v1/auth/whoami', headers=headers)

			if resp.status_code == 401:
				console.print('[error]Authentication failed: Invalid or expired token.[/error]')
				raise typer.Exit(1)

			resp.raise_for_status()
			return resp.json()
	except httpx.HTTPError as e:
		console.print(f'[error]Control Plane unreachable:[/error] {e}')
		raise typer.Exit(1) from e


def _select_project(projects: list[dict]) -> dict:
	"""
	Interactive terminal selection for Projects.
	"""
	if not projects:
		console.print('[warning]No projects found in your organization.[/warning]')
		console.print('Please create a project in the Ambyte Dashboard first.')
		raise typer.Exit(1)

	console.print('\n[bold]Select a Project to link to this workspace:[/bold]')
	for idx, p in enumerate(projects, 1):
		console.print(f'  {idx}. [cyan]{p["name"]}[/cyan] [dim]({p["id"]})[/dim]')

	choice = IntPrompt.ask('\nProject number', choices=[str(i) for i in range(1, len(projects) + 1)])
	return projects[choice - 1]


def _generate_machine_key(api_url: str, human_jwt: str, project_id: str) -> str:
	"""
	Exchanges a Human JWT for a persistent Machine API Key.
	"""
	headers = {'Authorization': f'Bearer {human_jwt}'}
	payload = {'name': f'CLI Key ({platform.uname().node})', 'scopes': ['admin']}

	try:
		with httpx.Client(timeout=10.0) as client:
			resp = client.post(f'{api_url.rstrip("/")}/v1/projects/{project_id}/keys', headers=headers, json=payload)
			resp.raise_for_status()
			return resp.json()['key']  # The sk_live_... value
	except Exception as e:
		console.print(f'[error]Failed to generate machine key:[/error] {e}')
		raise typer.Exit(1) from e


# ==============================================================================
# LOGIN COMMAND
# ==============================================================================


def login():
	"""
	Authenticate the CLI with the Ambyte Control Plane.
	"""
	auth_svc = CredentialsManager()
	config = None

	# 1. Initialize variables to None to satisfy static analysis
	final_api_key: str | None = None
	user_data: dict | None = None
	selected_project: dict | None = None

	# 1. Low-Overhead Check: Is AMBYTE_API_KEY already in the shell env?
	# This covers: System Env, .env file, and ~/.ambyte/credentials
	current_key = auth_svc.get_api_key()

	if current_key:
		# Check if it's specifically in the environment (Shell or .env)
		if os.getenv('AMBYTE_API_KEY'):
			console.print('[good]Already authenticated via environment variable (AMBYTE_API_KEY).[/good]')
		else:
			console.print('[good]Already authenticated via local credentials file.[/good]')
		return

	# 2. Workspace context (Proceed with menu if no key found)
	config = None
	try:
		config = load_config()
		base_url = str(config.cloud.url)
	except Exception:
		base_url = 'https://api.ambyte.ai'

	console.print(Panel.fit('[bold cyan]Ambyte Login[/bold cyan]\nConnect your terminal to the Control Plane.'))

	# 3. Present Menu
	console.print('[bold]? How would you like to authenticate?[/bold]')
	console.print('  1. Web Browser [dim](Fastest)[/dim]')
	console.print('  2. Device Code [dim](For remote servers/SSH)[/dim]')
	console.print('  3. Paste an existing API Key')

	choice = IntPrompt.ask('\nChoice', choices=['1', '2', '3'], default=1)

	final_api_key = None
	user_data = None

	# --- Choice 3: Manual Paste ---
	if choice == 3:
		final_api_key = Prompt.ask('Paste your Ambyte API Key', password=True)
		if not final_api_key.startswith('sk_'):
			console.print("[error]Invalid key format. Should start with 'sk_live_' or 'sk_test_'.[/error]")
			raise typer.Exit(1)

		with console.status('[info]Verifying key...[/info]'):
			user_data = _fetch_identity(base_url, final_api_key)

		selected_project = _select_project(user_data['projects'])

	# --- Choice 1: Web Browser ---
	elif choice == 1:
		oidc = OidcService()
		url, state = oidc.get_auth_url(base_url)

		oidc.open_browser(url)

		# 1. Capture the response (token + state)
		auth_data = oidc.wait_for_token()

		if not auth_data:
			raise typer.Exit(1)

		# 2. VALIDATION: Check that the returned state matches our original
		if auth_data.get('state') != state:
			console.print('[error]Security Error: State mismatch detected. Potential CSRF attempt.[/error]')
			raise typer.Exit(1)

		human_jwt = auth_data.get('token')

		if not human_jwt:
			console.print('[error]Authentication Error: Browser returned an empty token.[/error]')
			raise typer.Exit(1)

		with console.status('[info]Fetching your projects...[/info]'):
			user_data = _fetch_identity(base_url, human_jwt)

		selected_project = _select_project(user_data['projects'])

		with console.status('[info]Generating persistent machine key...[/info]'):
			final_api_key = _generate_machine_key(base_url, human_jwt, str(selected_project['id']))

	# --- Choice 2: Device Code ---
	elif choice == 2:
		console.print('\n[info]Device Code flow implementation coming soon.[/info]')  # TODO
		console.print(f'In the meantime, please visit: [highlight]{base_url}/settings/keys[/highlight]')
		console.print('Generate an API Key and use option [bold]3[/bold].\n')
		return

	# 4. Finalizing
	if final_api_key and user_data and selected_project:
		# If we didn't select a project (pasted key flow), do it now
		if choice == 3:
			selected_project = _select_project(user_data['projects'])

		# Save to ~/.ambyte/credentials
		auth_svc.save(
			api_key=final_api_key, project_id=str(selected_project['id']), org_id=str(user_data['organization_id'])
		)

		# Update local .ambyte/config.yaml if we are in a project
		if config:
			config.cloud.project_id = str(selected_project['id'])
			config.cloud.organization_id = str(user_data['organization_id'])
			save_config(config, get_workspace_root())

		console.print(f'\n[good]Success![/good] Authenticated as [bold]{user_data["user"]["email"]}[/bold]')
		console.print(f'Default project set to: [cyan]{selected_project["name"]}[/cyan]')


def push(
	file: Annotated[
		Path | None, typer.Option('--file', '-f', help='Push a specific policy file instead of the whole directory.')
	] = None,
	prune: Annotated[
		bool, typer.Option('--prune', '-p', help='Deactivate policies in the cloud that are missing locally.')
	] = False,
	dry_run: Annotated[
		bool, typer.Option('--dry-run', help='Simulate the push without making any changes in the cloud.')
	] = False,
	yes: Annotated[bool, typer.Option('--yes', '-y', help='Skip confirmation prompts.')] = False,
):
	"""
	Synchronize local obligations with the Ambyte Control Plane.

	This command:
	1. Validates local YAML syntax.
	2. Computes change hashes.
	3. Bulk upserts policies to the cloud.
	"""
	# 1. Load Environment & Auth Check
	config = load_config()
	if not config.cloud.project_id:
		console.print(
			'[error]No Project Linked.[/error] '
			'Run [bold]ambyte login[/bold] first to connect this workspace to the cloud.'
		)
		raise typer.Exit(1)

	loader = ObligationLoader(config)
	api = CloudApiClient(config)

	# 2. Pre-flight Validation
	console.print('[info]Scanning workspace for policies...[/info]')

	# We use the internal batch loader to get both valid obs and errors
	valid_obs, errors = loader._load_batch()

	if errors:
		console.print(f'\n[bad]✖ Validation Failed. Found {len(errors)} error(s):[/bad]')
		for err in errors:
			console.print(f'  • {err}')
		console.print('\n[error]Push aborted.[/error] Please fix the syntax errors above before syncing to the cloud.')
		raise typer.Exit(1)

	# 3. Logic Constraints
	if prune and file:
		console.print('[error]Constraint Error:[/error] Cannot use [bold]--prune[/bold] when pushing a single file.')
		console.print('Pruning requires a full directory sync to determine which policies to deactivate.')
		raise typer.Exit(1)

	if not valid_obs:
		console.print('[yellow]No policies found in the configured policies directory.[/yellow]')
		return

	# Filter if a specific file was requested
	if file:
		target_id = None
		# Try to find the ID of the specific file provided
		try:
			specific_ob = loader._load_file(file)
			target_id = specific_ob.id
			valid_obs = [ob for ob in valid_obs if ob.id == target_id]
		except Exception as e:
			console.print(f'[error]Could not load file {file}:[/error] {e}')
			raise typer.Exit(1) from e

		if not valid_obs:
			console.print(f'[error]File {file} not found in validated set.[/error]')
			raise typer.Exit(1)

	# 4. Confirmation for Prune
	if prune and not yes:
		if not Confirm.ask(
			'[warning]⚠️  Warning:[/warning] --prune will deactivate all cloud policies not '
			'found in your local directory. Continue?'
		):
			raise typer.Exit(0)

	# 5. Confirmation
	count = len(valid_obs)
	if not yes and not dry_run:
		confirm = typer.confirm(
			f"Ready to push {count} policy definitions to project '{config.project_name}'. Proceed?"
		)
		if not confirm:
			console.print('[neutral]Sync cancelled.[/neutral]')
			raise typer.Exit(0)

	# 6. The Network Sync
	try:
		label = 'Simulating sync' if dry_run else 'Syncing policies'
		with Progress(
			SpinnerColumn(),
			TextColumn('[progress.description]{task.description}'),
			transient=True,
		) as progress:
			progress.add_task(description=f'{label}...', total=None)

			# Prepare the JSON-serializable list
			payload = [ob.model_dump(mode='json', exclude_none=True) for ob in valid_obs]

			# Call our new API client
			results = api.push_obligations(payload)

		# 7. Success Reporting
		_print_push_summary(results, is_dry_run=dry_run)

	except Exception as e:
		# Error messages are handled inside api_client._handle_http_error
		raise typer.Exit(1) from e
	finally:
		api.close()


def _print_push_summary(summary: list[dict], is_dry_run: bool):
	"""Renders the sync results."""
	if is_dry_run:
		console.print('\n[highlight]DRY RUN MODE:[/highlight] No changes were applied to the cloud.\n')
	else:
		console.print('\n[good]✔ Sync Successful[/good]\n')

	table = Table(show_header=True, header_style='bold')
	table.add_column('Status')
	table.add_column('Policy ID', style='cyan')
	table.add_column('Version', justify='right')
	table.add_column('Title')

	status_map = {
		'CREATED': '[bold green]NEW[/bold green]',
		'UPDATED': '[bold yellow]CHANGED[/bold yellow]',
		'PRUNED': '[bold red]REMOVED[/bold red]',
		'UNCHANGED': '[dim]NO CHANGE[/dim]',
	}

	# Sort report: New/Updated first, then Pruned, then Unchanged
	order = {'CREATED': 0, 'UPDATED': 1, 'PRUNED': 2, 'UNCHANGED': 3}
	sorted_summary = sorted(summary, key=lambda x: order.get(x['status'], 99))

	for item in sorted_summary:
		table.add_row(status_map.get(item['status'], item['status']), item['slug'], str(item['version']), item['title'])

	console.print(table)

	# Final counts
	changed = sum(1 for x in summary if x['status'] in ['CREATED', 'UPDATED', 'PRUNED'])
	if changed == 0:
		console.print('\n[dim]Cloud is already up to date.[/dim]')
	else:
		console.print(f'\n[bold]{changed}[/bold] items modified.')

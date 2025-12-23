"""
CLI Commands for interacting with the Ambyte Cloud / Control Plane.
"""

import os
import platform

import httpx
import typer
from ambyte_cli.config import get_workspace_root, load_config, save_config
from ambyte_cli.services.auth import CredentialsManager
from ambyte_cli.services.oidc import OidcService
from ambyte_cli.ui.console import console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt

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

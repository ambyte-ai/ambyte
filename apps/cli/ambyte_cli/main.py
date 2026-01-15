"""
apps/cli/ambyte_cli/main.py
The main entry point for the Ambyte CLI.
"""

import logging

import typer
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

from ambyte_cli.commands import audit, check, cloud, core, project
from ambyte_cli.ui.console import console

# 1. Configure Global Rich Behavior
# ------------------------------------------------------------------------------
# Install Rich traceback handler so crashes are readable and syntax-highlighted.
install_rich_traceback(show_locals=False)


# 2. Define the Main Typer Application
# ------------------------------------------------------------------------------
app = typer.Typer(
	name='ambyte',
	help='[bold cyan]Ambyte Platform CLI[/bold cyan]\n\n'
	'Policy-as-Code for Data and AI pipelines.\n'
	'Define obligations, compile policies, and enforce them locally or in the cloud.',
	no_args_is_help=True,
	rich_markup_mode='rich',
	add_completion=True,
)


# 3. Register Commands
# ------------------------------------------------------------------------------
# We flatten the command structure for better Developer Experience (DX).
# Instead of `ambyte core build`, users type `ambyte build`.

# --- Project Group ---
app.command(name='init', help='Initialize a new Ambyte workspace in the current directory.')(project.init)
app.command(name='validate', help='Validate syntax of local obligation and resource definitions.')(project.validate)

# --- Core Loop (Local Logic) ---
app.command(name='build', help='Compile local obligations into enforcement artifacts (JSON/SQL/Rego).')(core.build)
app.command(name='resolve', help='Debug conflict resolution logic for a specific resource.')(core.resolve)
app.command(name='diff', help='Show semantic differences between current config and previous state.')(core.diff)

# --- Debugging & Testing ---
app.command(name='check', help='Simulate a permission check for an Actor/Resource.')(check.check)
app.command(name='why', help='Explain the provenance and reasoning behind a specific policy decision.')(check.why)

# --- Cloud / Enterprise ---
# We create a sub-typer for 'cloud' but alias common commands to root for speed.
cloud_app = typer.Typer(help='Manage interaction with the Ambyte Control Plane.')
app.add_typer(cloud_app, name='cloud')

app.command(name='login', help='Authenticate with the Ambyte Control Plane.')(cloud.login)
app.command(name='push', help='Push local policies to the Control Plane.')(cloud.push)
app.command(name='pull', help='Pull the latest obligations from the Control Plane.')(cloud.pull)

# --- Audit & Verification ---
audit_app = typer.Typer(help='Cryptographic verification tools.')
app.add_typer(audit_app, name='audit')
audit_app.command(name='verify')(audit.verify_log)


# 4. Global Callbacks & Configuration
# ------------------------------------------------------------------------------


def version_callback(value: bool):
	"""
	Prints the version and exits.
	"""
	if value:
		from importlib import metadata

		try:
			version = metadata.version('ambyte-cli')
		except metadata.PackageNotFoundError:
			version = 'dev'

		console.print(f'Ambyte CLI Version: [bold cyan]{version}[/bold cyan]')
		raise typer.Exit()


@app.callback()
def main(
	version: bool = typer.Option(
		None, '--version', '-v', callback=version_callback, is_eager=True, help='Show the version and exit.'
	),
	debug: bool = typer.Option(False, '--debug', help='Enable verbose debug logging.'),
):
	"""
	The Ambyte CLI entry point.
	"""
	# Configure Logging based on flags
	log_level = logging.DEBUG if debug else logging.INFO

	# We suppress noisy libraries unless we are in deep debug mode
	if not debug:
		logging.getLogger('httpx').setLevel(logging.WARNING)
		logging.getLogger('httpcore').setLevel(logging.WARNING)

	logging.basicConfig(
		level=log_level,
		format='%(message)s',
		datefmt='[%X]',
		handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=debug, markup=True)],
	)

	if debug:
		logging.debug('Debug logging enabled.')


# 5. Execution
# ------------------------------------------------------------------------------
if __name__ == '__main__':
	app()

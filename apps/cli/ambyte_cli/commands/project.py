"""
Commands related to project management and configuration.
"""

from pathlib import Path

import typer
from ambyte_cli.config import (
	CONFIG_DIR_NAME,
	AmbyteConfig,
	TargetPlatform,
	load_config,
	save_config,
)
from ambyte_cli.services.loader import ObligationLoader
from ambyte_cli.ui.console import console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

# Sample Obligation to get users started
SAMPLE_OBLIGATION_YAML = """# Ambyte Obligation Definition
# This file represents a legal or contractual constraint in code.

id: "gdpr-retention-standard"
title: "Standard GDPR Retention"
description: "Personal data should not be kept longer than necessary (Default: 3 years)."

# Where did this rule come from?
provenance:
    source_id: "GDPR"
    document_type: "REGULATION"
    section_reference: "Art. 5(1)(e)"
    document_uri: "https://gdpr-info.eu/art-5-gdpr/"

# How strict is this? (BLOCKING, AUDIT_ONLY, NOTIFY_HUMAN)
enforcement_level: "BLOCKING"

# The logic (Polymorphic: retention, geofencing, privacy, ai_model, etc.)
retention:
    duration: "1095d" # 3 years
    trigger: "CREATION_DATE"
    allow_legal_hold_override: true
"""  # noqa: E101

SAMPLE_RESOURCES_YAML = """# Ambyte Resource Inventory
# Define your data assets here so policies can be mapped to them.

resources:
  - urn: "urn:snowflake:prod:sales:customers"
    description: "Primary customer table in Snowflake"
    tags:
      domain: "sales"
      sensitivity: "high"
      contains_pii: "true"

  - urn: "urn:s3:data-lake:logs"
    description: "App logs bucket"
    tags:
      domain: "engineering"
      sensitivity: "low"
"""  # noqa: E101


def init(
	name: str = typer.Option(None, '--name', '-n', help='Name of the project. Defaults to current directory name.'),
	non_interactive: bool = typer.Option(False, '--yes', '-y', help='Skip prompts and use defaults.'),
):
	"""
	Initialize a new Ambyte workspace in the current directory.

	Scaffolds the .ambyte config directory, creates a 'policies' folder,
	and adds a sample obligation file.
	"""
	cwd = Path.cwd()
	config_dir = cwd / CONFIG_DIR_NAME

	# 1. Check for existing workspace
	if config_dir.exists():
		console.print(f'[yellow]Warning: An {CONFIG_DIR_NAME} directory already exists in this location.[/yellow]')
		if not non_interactive:
			if not Confirm.ask('Do you want to overwrite the existing configuration?'):
				console.print('[bold red]Aborted.[/bold red]')
				raise typer.Exit(1)

	# 2. Gather Configuration
	if name:
		project_name = name
	elif non_interactive:
		project_name = cwd.name
	else:
		console.print(
			Panel.fit("[bold cyan]Welcome to Ambyte![/bold cyan]\nLet's set up your compliance-as-code workspace.")
		)
		project_name = Prompt.ask('Project Name', default=cwd.name)

	# Ask for Targets (interactive only)
	targets = [TargetPlatform.LOCAL]
	if not non_interactive:
		if Confirm.ask('Do you want to generate SQL policies for Snowflake?'):
			targets.append(TargetPlatform.SNOWFLAKE)
		# We could add more prompts for OPA/IAM here, but let's keep it simple. # TODO

	# 3. Create Configuration Object
	config = AmbyteConfig(project_name=project_name, targets=targets)

	try:
		# 4. Write Config to Disk
		save_config(config, cwd)
		console.print(f'✅ Created [green]{CONFIG_DIR_NAME}/config.yaml[/green]')

		# 5. Scaffold Directories
		policies_dir = cwd / config.policies_dir
		artifacts_dir = cwd / config.artifacts_dir  # noqa: F841
		resources_dir = cwd / config.resources_dir

		if not policies_dir.exists():
			policies_dir.mkdir(parents=True)
			console.print(f'✅ Created [green]{config.policies_dir}/[/green]')

		# We don't create artifacts_dir yet; 'ambyte build' does that.

		# 6. Create Sample Policy
		sample_path = policies_dir / 'gdpr_sample.yaml'
		if not sample_path.exists():
			with open(sample_path, 'w', encoding='utf-8') as f:
				f.write(SAMPLE_OBLIGATION_YAML)
			console.print(f'✅ Created sample obligation: [green]{config.policies_dir}/gdpr_sample.yaml[/green]')

		# 7. Create Sample Inventory
		if not resources_dir.exists():
			resources_dir.mkdir(parents=True)
			console.print(f'✅ Created [green]{config.resources_dir}/[/green]')

		resource_path = resources_dir / 'resources.yaml'
		if not resource_path.exists():
			with open(resource_path, 'w', encoding='utf-8') as f:
				f.write(SAMPLE_RESOURCES_YAML)
			console.print(f'✅ Created sample inventory: [green]{config.resources_dir}/resources.yaml[/green]')

		# 8. Success Message
		console.print('\n[bold green]Workspace initialized successfully![/bold green]')
		console.print('Next steps:')
		console.print(f'  1. Review the sample policy: [cyan]cat {config.policies_dir}/gdpr_sample.yaml[/cyan]')
		console.print('  2. Compile it into executable artifacts: [cyan]ambyte build[/cyan]')
		console.print('  3. Check a hypothetical permission: [cyan]ambyte check --resource urn:snowflake:...[/cyan]')

	except Exception as e:
		console.print(f'[bold red]Failed to initialize workspace:[/bold red] {e}')
		raise typer.Exit(1) from None


def validate():
	"""
	Validate the syntax of local obligation and resource definitions.
	"""
	try:
		# 1. Load Config (Raises if not found/invalid)
		config = load_config()

		console.print(f'[dim]Scanning policies in {config.abs_policies_dir}...[/dim]')

		# 2. Initialize Loader
		loader = ObligationLoader(config)

		# 3. Attempt Load
		# The loader prints individual file errors to the console automatically.
		obligations = loader.load_all()

		# 4. Summary Report
		if not obligations:
			console.print('[yellow]No valid obligations found.[/yellow]')
			# We exit with error if no valid files were found, assuming the user expected some.
			raise typer.Exit(1)

		console.print(f'\n[bold green]Success![/bold green] Validated {len(obligations)} obligation(s).')
		console.print('Run [cyan]ambyte build[/cyan] to generate artifacts.')

	except FileNotFoundError:
		console.print('[bold red]Not an Ambyte workspace.[/bold red] Run [cyan]ambyte init[/cyan] first.')
		raise typer.Exit(1) from None
	except Exception as e:
		console.print(f'[bold red]Validation failed:[/bold red] {e}')
		raise typer.Exit(1) from None

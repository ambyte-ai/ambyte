"""
Core logic commands: resolve, build, and diff.
"""

import importlib.util
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer
from ambyte_cli.config import (
	AmbyteConfig,
	TargetPlatform,
	get_workspace_root,
	load_config,
)
from ambyte_cli.services.git import GitHistoryLoader
from ambyte_cli.services.inventory import InventoryLoader
from ambyte_cli.services.loader import ObligationLoader
from ambyte_cli.ui.console import console
from ambyte_compiler.diff_engine.models import ChangeImpact
from ambyte_compiler.diff_engine.service import SemanticDiffEngine
from ambyte_compiler.matcher import ResourceMatcher
from ambyte_compiler.service import PolicyCompilerService
from ambyte_rules.engine import ConflictResolutionEngine
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)


def _load_resource_context(urn: str) -> dict[str, Any]:
	"""
	Helper to find tags for a specific URN from the resources.yaml inventory.
	Returns a dictionary: {'urn': ..., 'tags': {...}}
	"""
	try:
		root = get_workspace_root()
		inv_loader = InventoryLoader(root)
		resources = inv_loader.load()

		# Find matching resource
		for r in resources:
			if r.urn == urn:
				return {'urn': r.urn, 'tags': r.tags}

		# Fallback: Return empty tags if not in inventory
		return {'urn': urn, 'tags': {}}
	except Exception:
		# If inventory fails to load, proceed with empty context
		return {'urn': urn, 'tags': {}}


def resolve(
	resource_urn: str = typer.Argument(..., help='The Unique Resource Name (URN) to resolve policy for.'),
	json_out: bool = typer.Option(False, '--json', help='Output raw JSON instead of formatted tables.'),
):
	"""
	Debug conflict resolution logic for a specific resource.

	1. Looks up the Resource in resources.yaml to get Tags.
	2. Matches Obligations against URN + Tags.
	3. Resolves conflicts to show the Effective Policy.
	"""
	try:
		# 1. Setup Environment
		config = load_config()
		obl_loader = ObligationLoader(config)

		# 2. Load Definitions
		if not json_out:
			with console.status('[bold green]Loading obligations...[/bold green]'):
				obligations = obl_loader.load_all()

		else:
			obligations = obl_loader.load_all()

		if not obligations:
			console.print('[yellow]No obligations found. Nothing to resolve.[/yellow]')
			raise typer.Exit(1)

		# 3. Load Resource Context (Tags)
		resource_ctx = _load_resource_context(resource_urn)
		tags = resource_ctx.get('tags', {})

		if not json_out:
			if tags:
				console.print(f'[dim]Found tags for {escape(resource_urn)}: {tags}[/dim]', emoji=False)
			else:
				console.print(
					f'[dim]No tags found in inventory for {escape(resource_urn)}. Assuming empty context.[/dim]',
					emoji=False,
				)

		# 4. Match (Filter Global -> Local)
		matcher = ResourceMatcher()
		applicable = [ob for ob in obligations if matcher.matches(resource_urn, tags, ob)]

		if not json_out:
			console.print(f'[dim]Matched {len(applicable)}/{len(obligations)} obligations.[/dim]')

		# 5. Run Engine
		engine = ConflictResolutionEngine()
		resolved_policy = engine.resolve(resource_urn, applicable)

		# 6. Output
		if json_out:
			console.print_json(resolved_policy.model_dump_json())
		else:
			_print_resolved_pretty(resolved_policy)

	except Exception as e:
		console.print(f'[bold red]Resolution failed:[/bold red] {e}')
		raise typer.Exit(1) from None


def build(clean: bool = typer.Option(False, '--clean', help='Clear existing artifacts before building.')):
	"""
	Compile local obligations into enforcement artifacts (JSON/SQL/Rego).

	The output directory is defined in .ambyte/config.yaml (default: .ambyte/dist).
	"""
	try:
		config = load_config()
		obl_loader = ObligationLoader(config)
		inv_loader = InventoryLoader(get_workspace_root())
		out_dir = config.abs_artifacts_dir

		# 1. Clean previous build
		if clean and out_dir.exists():
			shutil.rmtree(out_dir)
			console.print(f'[dim]Cleaned {out_dir}[/dim]')

		out_dir.mkdir(parents=True, exist_ok=True)

		# 2. Load Data
		with console.status('[bold green]Loading inputs...[/bold green]'):
			obligations = obl_loader.load_all()

			# Load Inventory (resources.yaml)
			# Convert Pydantic models to list of dicts for the compiler service
			inventory_models = inv_loader.load()
			resources = [{'urn': r.urn, 'tags': r.tags, 'config': r.config} for r in inventory_models]

			if not obligations:
				console.print('[yellow]No obligations found. Nothing to build.[/yellow]')
				raise typer.Exit(0)

			if not resources:
				console.print('[yellow]No resources found in inventory. Using default wildcard context.[/yellow]')
				resources = [{'urn': 'urn:local:default', 'tags': {}, 'config': {}}]

		# 3. Initialize Compiler Service
		template_path = _get_template_path()
		compiler = PolicyCompilerService(templates_path=template_path)

		console.print(f'Building for targets: [cyan]{", ".join(config.targets)}[/cyan]')
		console.print(f'Processing [bold]{len(resources)}[/bold] resources.')

		# --- Target: LOCAL (JSON for Python SDK) ---
		if TargetPlatform.LOCAL in config.targets:
			_build_local(compiler, resources, obligations, config)

		# --- Target: SNOWFLAKE (SQL) ---
		if TargetPlatform.SNOWFLAKE in config.targets:
			_build_snowflake(compiler, resources, obligations, out_dir)

		# --- Target: OPA (Data Bundle) ---
		if TargetPlatform.OPA in config.targets:
			_build_opa(compiler, resources, obligations, out_dir)

		# --- Target: AWS IAM ---
		if TargetPlatform.AWS_IAM in config.targets:
			_build_iam(compiler, resources, obligations, out_dir)

		console.print(f'\n✅ Build complete! Artifacts in [green]{out_dir}[/green]')

	except Exception as e:
		console.print(f'[bold red]Build failed:[/bold red] {e}')
		raise typer.Exit(1) from None


def diff(
	reference: str = typer.Option('HEAD', help='The git reference to compare against (e.g., HEAD~1, main).'),
	resource: str = typer.Option('urn:ambyte:diff-target', help='The Resource URN to resolve policies against.'),
	markdown: bool = typer.Option(False, '--md', help='Output raw Markdown instead of rendered tables.'),
):
	"""
	Show semantic differences between current config and a previous git state.
	"""
	try:
		config = load_config()

		# 1. Load Current State
		current_loader = ObligationLoader(config)
		with console.status('[bold green]Loading current obligations...[/bold green]'):
			current_obs = current_loader.load_all()

		# 2. Load Old State
		git_loader = GitHistoryLoader(config)
		try:
			with console.status(f'[bold blue]Loading obligations from {reference}...[/bold blue]'):
				old_obs = git_loader.load_at_revision(reference)
		except ValueError as e:
			console.print(f'[bold red]Git Error:[/bold red] {e}')
			raise typer.Exit(1) from e

		if not current_obs and not old_obs:
			console.print('[yellow]No obligations found in either current or previous state.[/yellow]')
			raise typer.Exit(0)

		# 3. Load Context (Tags) for the specific resource
		# We use the CURRENT inventory state for both to see how policy changes affect *this* resource.
		resource_ctx = _load_resource_context(resource)
		tags = resource_ctx.get('tags', {})

		# 4. Match & Resolve (Current vs Old)
		matcher = ResourceMatcher()
		engine = ConflictResolutionEngine()

		# Current Policy
		curr_filtered = [o for o in current_obs if matcher.matches(resource, tags, o)]
		policy_now = engine.resolve(resource, curr_filtered)

		# Old Policy (applied to current resource context)
		old_filtered = [o for o in old_obs if matcher.matches(resource, tags, o)]
		policy_then = engine.resolve(resource, old_filtered)

		# 5. Compute Semantic Diff
		diff_engine = SemanticDiffEngine()
		report = diff_engine.compute_diff(policy_then, policy_now)

		# 6. Render Output
		if markdown:
			console.print(report.to_markdown())
		else:
			_print_diff_report(report, reference)

	except Exception as e:
		console.print(f'[bold red]Diff failed:[/bold red] {e}')
		raise typer.Exit(1) from None


# ==============================================================================
# Build Logic Helpers
# ==============================================================================


def _build_local(compiler: PolicyCompilerService, resources: list[dict], obligations: list, config: AmbyteConfig):
	"""
	Generates the local_policies.json Bundle.
	The compiler handles bulk resolution for 'local' target internally.
	"""
	console.print('  • Generating [bold]Local Policy Bundle[/bold]...', end='')

	out_dir = config.abs_artifacts_dir

	# Context for metadata
	git_hash = None
	try:
		git_path = shutil.which('git')
		if git_path:
			git_hash = (
				subprocess.check_output([git_path, 'rev-parse', '--short', 'HEAD'], stderr=subprocess.DEVNULL)  # noqa: S603
				.decode()
				.strip()
			)
	except subprocess.CalledProcessError:
		# Not a git repo or git command failed; this is expected in some envs (e.g. docker, smoke tests)
		logger.debug('Could not retrieve git hash (likely not a git repository).')
		pass
	except Exception:
		logger.warning('Failed to get git hash for build metadata.', exc_info=False)
		pass

	context = {'project_name': config.project_name, 'git_hash': git_hash}

	# Compiler Call
	bundle_json = compiler.compile(resources=resources, obligations=obligations, target='local', context=context)

	# Write to Disk
	out_file = out_dir / 'local_policies.json'
	with open(out_file, 'w', encoding='utf-8') as f:
		f.write(str(bundle_json))

	console.print(' [green]Done[/green]')


def _build_snowflake(compiler: PolicyCompilerService, resources: list[dict], obligations: list, out_dir: Path):
	"""
	Generates masking policy SQL.
	Merges resource-specific config with defaults.
	"""
	console.print('  • Generating [bold]Snowflake SQL[/bold]...', end='')

	# Global Defaults
	default_ctx = {'input_type': 'VARCHAR', 'allowed_roles': ['ADMIN', 'PII_READER']}

	all_sql = []

	for res in resources:
		urn = res['urn']

		# Simple heuristic filter
		if 'snowflake' not in urn and 'db' not in urn:
			continue

		# 1. Merge Config
		# Priority: Resource Config > Default
		res_config = res.get('config', {}).get('snowflake', {})

		# Shallow merge
		ctx = default_ctx.copy()
		ctx.update(res_config)

		try:
			# Pass single resource list
			sql = compiler.compile(resources=[res], obligations=obligations, target='snowflake', context=ctx)
			if sql and 'No active' not in str(sql):
				all_sql.append(f'-- Resource: {urn}\n{sql}')
		except Exception as e:
			logger.warning(f'Failed to compile SQL for {urn}: {e}')

	out_file = out_dir / 'masking_policies.sql'
	with open(out_file, 'w', encoding='utf-8') as f:
		f.write('\n\n'.join(all_sql))

	console.print(' [green]Done[/green]')


def _build_opa(compiler: PolicyCompilerService, resources: list[dict], obligations: list, out_dir: Path):
	"""
	Generates data.json for OPA.
	Creates a dictionary of { "urn": { policy... } }
	"""
	console.print('  • Generating [bold]OPA Bundle[/bold]...', end='')

	master_bundle = {}

	for res in resources:
		try:
			data = compiler.compile(resources=[res], obligations=obligations, target='opa')
			if isinstance(data, dict):
				master_bundle[res['urn']] = data
		except Exception as e:
			logger.warning(f'Failed to compile OPA for {res["urn"]}: {e}')

	out_file = out_dir / 'data.json'
	with open(out_file, 'w', encoding='utf-8') as f:
		# Wrap in a root key for cleaner Rego lookup: data.ambyte.policies[urn]
		json.dump({'policies': master_bundle}, f, indent=2, default=str)

	console.print(' [green]Done[/green]')


def _build_iam(compiler: PolicyCompilerService, resources: list[dict], obligations: list, out_dir: Path):
	"""
	Generates AWS IAM Policy JSONs.
	Creates one file per resource (e.g., iam_my-bucket.json).
	"""
	console.print('  • Generating [bold]AWS IAM Policies[/bold]...', end='')

	generated_count = 0

	for res in resources:
		urn = str(res['urn'])
		# Filter: Only process AWS-looking URNs
		if 'aws' not in urn and not urn.startswith('arn:'):
			continue

		try:
			# Determine Policy Type: Resource (Bucket) vs Identity (Guardrail)
			policy_type = 'identity'
			if ':s3:::' in urn:
				policy_type = 'resource'

			ctx: dict[str, str | list[str]] = {
				'resource_arn': urn,  # We use the URN as the ARN for CLI context
				'iam_policy_type': policy_type,
			}

			# Compile
			policy_json = compiler.compile(resources=[res], obligations=obligations, target='aws_iam', context=ctx)

			# Validate output isn't empty wrapper
			if not policy_json:
				continue

			# Clean filename: arn:aws:s3:::my-bucket -> iam_my-bucket.json
			# arn:aws:iam::123:role/MyRole -> iam_MyRole.json
			safe_name = urn.split(':')[-1].replace('/', '_')
			filename = f'iam_{safe_name}.json'

			with open(out_dir / filename, 'w', encoding='utf-8') as f:
				f.write(str(policy_json))

			generated_count += 1

		except Exception as e:
			logger.warning(f'Failed to generate IAM policy for {urn}: {e}')

	console.print(f' [green]Done ({generated_count} files)[/green]')


def _get_template_path() -> Path:
	"""
	Locates the SQL templates directory.
	"""
	from ambyte_cli.config import get_workspace_root

	try:
		root = get_workspace_root()

		# 1. Dev/Monorepo path (Source-based resolution)
		# Correctly locate repo root relative to this file (core.py)
		# Path: apps/cli/ambyte_cli/commands/core.py -> ../../../../.. -> repo_root
		current_file = Path(__file__).resolve()
		# Protect against index errors if path is too short
		if len(current_file.parents) >= 5:
			repo_root = current_file.parents[4]
			candidate = repo_root / 'policy-library' / 'sql_templates'
			if candidate.exists():
				return candidate

		# 2. User Workspace path (scaffolded)
		candidate = root / 'templates'
		if candidate.exists():
			return candidate

		# 3. Installed package path (Pip Install)
		# Checks if templates are bundled inside ambyte_cli
		spec = importlib.util.find_spec('ambyte_cli')
		if spec and spec.origin:
			package_root = Path(spec.origin).parent
			# Standard bundling: ambyte_cli/templates/sql_templates
			candidate = package_root / 'templates' / 'sql_templates'
			if candidate.exists():
				return candidate

			# Fallback for some editable installs or flat layouts
			candidate = package_root / 'sql_templates'
			if candidate.exists():
				return candidate

	except Exception:
		logger.warning('Failed to locate template path, falling back to default.', exc_info=True)
		pass

	return Path('policy-library/sql_templates')


# ==============================================================================
# UI Helpers
# ==============================================================================


def _print_diff_report(report, reference_name):
	"""Renders the PolicyDiffReport as a Rich UI."""

	if not report.has_changes:
		console.print(
			Panel(
				f'✅ No semantic policy changes detected since [bold cyan]{reference_name}[/bold cyan].',
				border_style='green',
			)
		)
		return

	# Header
	score = report.risk_score_delta
	if score > 0:
		header = f'⚠️  Risk Profile INCREASED (+{score})'
		style = 'yellow'
	elif score < 0:
		header = f'🛡️  Risk Profile Decreased ({score})'
		style = 'green'
	else:
		header = 'ℹ️  Risk Profile Neutral'
		style = 'blue'

	console.print(Panel(header, style=style, title=f'Diff vs {reference_name}'))

	# Table
	table = Table(show_header=True, header_style='bold')
	table.add_column('Category')
	table.add_column('Change')
	table.add_column('Field')
	table.add_column('Description')

	icon_map = {
		ChangeImpact.PERMISSIVE: '[red]🔓 Looser[/red]',
		ChangeImpact.RESTRICTIVE: '[green]🔒 Stricter[/green]',
		ChangeImpact.NEUTRAL: '[blue]📝 Info[/blue]',
	}

	for c in report.changes:
		table.add_row(c.category, icon_map[c.impact], f'[dim]{c.field}[/dim]', c.description)

	console.print(table)

	# Summary of sources
	console.print(
		f'\nObligations Active: [bold]{len(report.new_obligation_ids)}[/bold] (Was: {len(report.old_obligation_ids)})'
	)


def _print_resolved_pretty(policy):
	"""Prints a user-friendly report of the ResolvedPolicy."""
	safe_urn = escape(policy.resource_urn)
	console.print(Panel(f'[bold cyan]Effective Policy: {safe_urn}[/bold cyan]'), emoji=False)

	# 1. Retention
	if policy.retention:
		table = Table(title='Retention Policy', show_header=False, box=None)
		table.add_row('Duration', str(policy.retention.duration))
		trigger_display = getattr(policy.retention.trigger, 'name', str(policy.retention.trigger))
		table.add_row('Trigger', trigger_display)
		table.add_row('Legal Hold', '[red]Active[/red]' if policy.retention.is_indefinite else 'None')
		table.add_row(
			'[dim]Winner[/dim]',
			f'[dim]{policy.retention.reason.winning_source_id} ({policy.retention.reason.winning_obligation_id})[/dim]',
		)
		console.print(table)
	else:
		console.print('[dim]No Retention rules active.[/dim]')

	console.print('')

	# 2. Geofencing
	if policy.geofencing:
		table = Table(title='Geofencing Policy', show_header=False, box=None)

		allowed = ', '.join(policy.geofencing.allowed_regions) or 'All'
		blocked = ', '.join(policy.geofencing.blocked_regions) or 'None'

		if policy.geofencing.is_global_ban:
			table.add_row('Status', '[bold red]GLOBAL BAN[/bold red]')
		else:
			table.add_row('Allowed', f'[green]{allowed}[/green]')
			table.add_row('Blocked', f'[red]{blocked}[/red]')

		table.add_row('[dim]Winner[/dim]', f'[dim]{policy.geofencing.reason.winning_source_id}[/dim]')
		console.print(table)
	else:
		console.print('[dim]No Geofencing rules active.[/dim]')

	console.print('')

	# 3. AI Rules
	if policy.ai_rules:
		table = Table(title='AI Model Constraints', show_header=False, box=None)

		def fmt_bool(b):
			return '[green]Allowed[/green]' if b else '[red]Blocked[/red]'

		table.add_row('Training', fmt_bool(policy.ai_rules.training_allowed))
		table.add_row('Fine-Tuning', fmt_bool(policy.ai_rules.fine_tuning_allowed))
		table.add_row('RAG', fmt_bool(policy.ai_rules.rag_allowed))

		if policy.ai_rules.attribution_required:
			table.add_row('Attribution', f'[yellow]Required[/yellow]: {policy.ai_rules.attribution_text}')

		table.add_row('[dim]Winner[/dim]', f'[dim]{policy.ai_rules.reason.winning_source_id}[/dim]')
		console.print(table)
	else:
		console.print('[dim]No AI rules active.[/dim]')

	console.print('')

	# 4. Purpose Restrictions
	if policy.purpose:
		table = Table(title='Purpose Restrictions', show_header=False, box=None)

		allowed = ', '.join(sorted(policy.purpose.allowed_purposes)) or 'Any (Open)'
		denied = ', '.join(sorted(policy.purpose.denied_purposes)) or 'None'

		table.add_row('Allowed', f'[green]{allowed}[/green]')
		table.add_row('Denied', f'[red]{denied}[/red]')
		table.add_row(
			'[dim]Winner[/dim]',
			f'[dim]{policy.purpose.reason.winning_source_id}[/dim]',
		)
		console.print(table)
	else:
		console.print('[dim]No Purpose rules active.[/dim]')

	console.print('')

	# 5. Privacy Enhancements
	if policy.privacy:
		table = Table(title='Privacy Enhancements', show_header=False, box=None)

		table.add_row('Method', f'[bold magenta]{policy.privacy.method.name}[/bold magenta]')

		if policy.privacy.parameters:
			params_str = ', '.join(f'{k}={v}' for k, v in policy.privacy.parameters.items())
			table.add_row('Config', f'[cyan]{params_str}[/cyan]')

		table.add_row('[dim]Winner[/dim]', f'[dim]{policy.privacy.reason.winning_source_id}[/dim]')
		console.print(table)
	else:
		console.print('[dim]No Privacy rules active.[/dim]')

"""
Core logic commands: resolve, build, and diff.
"""

import json
import logging
from pathlib import Path

import typer
from ambyte_cli.config import TargetPlatform, load_config
from ambyte_cli.services.git import GitHistoryLoader
from ambyte_cli.services.loader import ObligationLoader
from ambyte_rules.engine import ConflictResolutionEngine
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from apps.policy_compiler.ambyte_compiler.diff_engine.models import ChangeImpact
from apps.policy_compiler.ambyte_compiler.diff_engine.service import SemanticDiffEngine
from apps.policy_compiler.ambyte_compiler.service import PolicyCompilerService

console = Console()

logger = logging.getLogger(__name__)


def resolve(
	resource_urn: str = typer.Argument(..., help='The Unique Resource Name (URN) to resolve policy for.'),
	json: bool = typer.Option(False, '--json', help='Output raw JSON instead of formatted tables.'),
):
	"""
	Debug conflict resolution logic for a specific resource.

	Loads all local obligations, feeds them into the Rules Engine,
	and displays the final "Effective Policy" along with the
	winning reasons (ConflictTrace).
	"""
	try:
		# 1. Setup Environment
		config = load_config()
		loader = ObligationLoader(config)

		# 2. Load Definitions
		with console.status('[bold green]Loading obligations...[/bold green]'):
			obligations = loader.load_all()

		if not obligations:
			console.print('[yellow]No obligations found. Nothing to resolve.[/yellow]')
			raise typer.Exit(1)

		# 3. Run Engine
		# Note: In a real system, we would first filter 'obligations' to only those
		# applicable to 'resource_urn' (via Tags/Attributes). # TODO
		# For the Local CLI MVP, we treat the 'policies/' folder as the active context.
		engine = ConflictResolutionEngine()
		resolved_policy = engine.resolve(resource_urn, obligations)

		# 4. Output
		if json:
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
		loader = ObligationLoader(config)
		out_dir = config.abs_artifacts_dir

		# 1. Clean previous build
		if clean and out_dir.exists():
			import shutil

			shutil.rmtree(out_dir)
			console.print(f'[dim]Cleaned {out_dir}[/dim]')

		out_dir.mkdir(parents=True, exist_ok=True)

		# 2. Load & Validate
		with console.status('[bold green]Loading obligations...[/bold green]'):
			obligations = loader.load_all()
			if not obligations:
				console.print('[yellow]No obligations found. Nothing to build.[/yellow]')
				raise typer.Exit(0)

		# 3. Initialize Compiler Service
		# We need to find the templates directory relative to the package installation
		# For dev mode, we look relative to the repo root logic in config
		template_path = _get_template_path()
		compiler = PolicyCompilerService(templates_path=template_path)

		console.print(f'Building for targets: [cyan]{", ".join(config.targets)}[/cyan]')

		# 4. Generate Artifacts
		# For MVP, we assume a single 'global' resource context for the Local Target,
		# or we iterate over a hypothetical 'resources.yaml' (omitted for brevity).
		# We'll generate a wildcard policy for "urn:local:*" to prove the flow. # TODO

		# --- Target: LOCAL (JSON for Python SDK) ---
		if TargetPlatform.LOCAL in config.targets:
			_build_local(compiler, obligations, out_dir)

		# --- Target: SNOWFLAKE (SQL) ---
		if TargetPlatform.SNOWFLAKE in config.targets:
			_build_snowflake(compiler, obligations, out_dir)

		# --- Target: OPA (Data Bundle) ---
		if TargetPlatform.OPA in config.targets:
			_build_opa(compiler, obligations, out_dir)

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

	This command:
	1. Loads current obligations from disk.
	2. Loads historic obligations from git `reference`.
	3. Resolves both sets into Effective Policies for the target `resource`.
	4. Computes the semantic diff (e.g. "Risk Increased", "Retention Reduced").
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

		# 3. Resolve Policies
		# We need to turn lists of obligations into a mathematical truth (ResolvedPolicy)
		# so we can compare the *effect*, not just the text files.
		rules_engine = ConflictResolutionEngine()

		policy_now = rules_engine.resolve(resource, current_obs)
		policy_then = rules_engine.resolve(resource, old_obs)

		# 4. Compute Semantic Diff
		diff_engine = SemanticDiffEngine()
		report = diff_engine.compute_diff(policy_then, policy_now)

		# 5. Render Output
		if markdown:
			console.print(report.to_markdown())
		else:
			_print_diff_report(report, reference)

	except Exception as e:
		console.print(f'[bold red]Diff failed:[/bold red] {e}')
		# In debug mode, we might want to raise to see traceback
		# raise e
		raise typer.Exit(1) from None


# ==============================================================================
# Build Logic Helpers
# ==============================================================================


def _build_local(compiler: PolicyCompilerService, obligations: list, out_dir: Path):
	"""Generates the policy.json used by ambyte-sdk in LOCAL mode."""
	console.print('  • Generating [bold]Local JSON[/bold]...', end='')

	# In Local Mode, we create a map of URN -> Decision
	# Since we don't have a resource inventory in the CLI yet, we compile
	# a "default" policy that applies to everything.
	# The SDK's Local Engine expects: { "urn": { "action": "ALLOW" } }

	# We resolve against a generic placeholder to get the constraints
	policy = compiler.compile(  # noqa: F841
		resource_urn='urn:local:default',
		obligations=obligations,
		target='opa',  # We reuse OPA dict output structure for now, or raw ResolvedPolicy
	)

	# Since the Compiler's 'compile' method returns different things based on target,
	# let's use the rules engine directly for the raw object, then serialize.
	# Ideally, we'd have a specific TargetPlatform.LOCAL in the compiler service too.

	# Hack for MVP: We serialize the raw ResolvedPolicy # TODO
	resolved = compiler.rules_engine.resolve('urn:local:default', obligations)  # noqa: F841

	# We construct the specific format expected by ambyte.core.decision._execute_local
	# That simplistic engine expects: { "urn": { "action": "ALLOW" } }
	# But a real policy is more complex.
	# Let's write the FULL ResolvedPolicy to 'policy.json' and assume
	# the SDK will evolve to read it (Phase 2). # TODO

	# For now, let's just write the OPA bundle logic which is JSON compatible
	bundle = compiler.compile('urn:local:default', obligations, 'opa')

	out_file = out_dir / 'policy.json'
	with open(out_file, 'w', encoding='utf-8') as f:
		json.dump(bundle, f, indent=2, default=str)

	console.print(' [green]Done[/green]')


def _build_snowflake(compiler: PolicyCompilerService, obligations: list, out_dir: Path):
	"""Generates masking policy SQL."""
	console.print('  • Generating [bold]Snowflake SQL[/bold]...', end='')

	# Example context. In a real CLI, this might come from --context or a resources.yaml # TODO
	ctx = {'input_type': 'VARCHAR', 'allowed_roles': ['ADMIN', 'PII_READER']}

	sql = compiler.compile(
		resource_urn='urn:snowflake:example', obligations=obligations, target='snowflake', context=ctx
	)

	out_file = out_dir / 'masking_policies.sql'
	with open(out_file, 'w', encoding='utf-8') as f:
		f.write(str(sql))

	console.print(' [green]Done[/green]')


def _build_opa(compiler: PolicyCompilerService, obligations: list, out_dir: Path):
	"""Generates data.json for OPA."""
	console.print('  • Generating [bold]OPA Bundle[/bold]...', end='')

	data = compiler.compile(resource_urn='urn:opa:example', obligations=obligations, target='opa')

	out_file = out_dir / 'data.json'
	with open(out_file, 'w', encoding='utf-8') as f:
		json.dump(data, f, indent=2, default=str)

	console.print(' [green]Done[/green]')


def _get_template_path() -> Path:
	"""
	Locates the SQL templates directory.
	Attempts to find 'policy-library/sql_templates' relative to the project root.
	"""
	# 1. Try generic project structure (dev mode)
	# The config helper knows where the root is
	from ambyte_cli.config import get_workspace_root

	try:
		root = get_workspace_root()
		# In the monorepo, it is at root/policy-library
		# But if the user ran 'ambyte init' in a subfolder, get_workspace_root is that subfolder.
		# This implies 'policy-library' must exist inside the user's workspace
		# OR be embedded in the installed python package.

		# STRATEGY: Look in python package first (installed mode)
		import apps.policy_compiler

		package_root = Path(apps.policy_compiler.__file__).parent  # noqa: F841
		# Assuming templates are packaged inside the compiler during build
		# (This requires pyproject.toml adjustments to include data files)
		# For now, let's fallback to the dev path in the monorepo logic # TODO

		# Hardcoded dev check for this environment
		repo_root = root.parent.parent  # apps/cli -> root
		candidate = repo_root / 'policy-library' / 'sql_templates'
		if candidate.exists():
			return candidate

		# Fallback to local workspace if user copied them
		candidate = root / 'templates'
		if candidate.exists():
			return candidate

	except Exception:
		logger.warning('Failed to locate template path, falling back to default.', exc_info=True)
		pass

	# Default fail-safe for the test environment context
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
		ChangeImpact.PERMISSIVE: '[red]🔓 Looser[/red]',  # Permissive is risky
		ChangeImpact.RESTRICTIVE: '[green]🔒 Stricter[/green]',  # Restrictive is safe
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
	console.print(Panel(f'[bold cyan]Effective Policy: {policy.resource_urn}[/bold cyan]'))

	# 1. Retention
	if policy.retention:
		table = Table(title='Retention Policy', show_header=False, box=None)
		table.add_row('Duration', str(policy.retention.duration))
		table.add_row('Trigger', str(policy.retention.trigger))
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

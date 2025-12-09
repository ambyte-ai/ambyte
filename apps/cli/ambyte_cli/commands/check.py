"""
Debug commands for simulating policy enforcement.
"""

import json
from datetime import datetime, timezone
from typing import Any

import typer
from ambyte_cli.config import load_config, get_workspace_root
from ambyte_cli.services.inventory import InventoryLoader
from ambyte_cli.services.loader import ObligationLoader
from ambyte_cli.ui.console import console
from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ConflictTrace, ResolvedPolicy
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from apps.policy_compiler.ambyte_compiler.matcher import ResourceMatcher


def _load_resource_tags(urn: str) -> dict[str, str]:
	"""
	Helper to find static tags for a specific URN from the resources.yaml inventory.
	"""
	try:
		root = get_workspace_root()
		inv_loader = InventoryLoader(root)
		# InventoryLoader handles missing files gracefully
		resources = inv_loader.load()

		for r in resources:
			if r.urn == urn:
				return r.tags

		# Not found in inventory
		return {}
	except Exception:
		# If inventory logic fails, proceed with empty tags (Global matches only)
		return {}


def check(
	resource: str = typer.Option(..., '--resource', '-r', help='The URN of the resource to access.'),
	action: str = typer.Option(..., '--action', '-a', help='The action to perform (e.g. read, train, query).'),
	actor: str = typer.Option('anonymous', '--actor', help='The ID of the user/service performing the action.'),
	context: str = typer.Option(
		'{}', '--context', '-c', help='JSON string of runtime context variables (e.g. \'{"region": "US"}\').'
	),
	verbose: bool = typer.Option(False, '--verbose', '-v', help='Show detailed decision logic.'),
):
	"""
	Simulate a permission check: "Can Actor X do Action Y on Resource Z?"

	This command:
	1. Loads local Obligations.
	2. Loads Resource Tags from inventory (resources.yaml).
	3. Matches Obligations to Resource.
	4. Resolves conflicts.
	5. Evaluates the Effective Policy against the provided runtime context.
	"""
	try:
		# 1. Parse Inputs
		try:
			runtime_ctx = json.loads(context)
		except json.JSONDecodeError as e:
			console.print('[bold red]Error:[/bold red] --context must be valid JSON.')
			raise typer.Exit(1) from e

		# 2. Load Environment
		config = load_config()
		loader = ObligationLoader(config)

		with console.status('[dim]Compiling policies...[/dim]'):
			# A. Load All Raw Obligations
			all_obligations = loader.load_all()
			if not all_obligations:
				console.print('[yellow]No obligations defined. Defaulting to ALLOW (Open).[/yellow]')
				_print_result(True, 'No constraints found.')
				return

			# B. Load Resource Metadata (Tags)
			resource_tags = _load_resource_tags(resource)
			if resource_tags:
				console.print(f'[dim]Applied tags from inventory: {resource_tags}[/dim]')
			else:
				console.print(f'[dim]No inventory tags found for {resource}. Only matching global (*) policies.[/dim]')

			# C. Match Applicable Obligations
			matcher = ResourceMatcher()
			applicable_obligations = [ob for ob in all_obligations if matcher.matches(resource, resource_tags, ob)]

			# D. Resolve Conflicts
			engine = ConflictResolutionEngine()
			policy = engine.resolve(resource, applicable_obligations)

		# 3. Simulate Enforcement
		# The Simulator uses the policy (WHAT rules apply) and the runtime_ctx (WHAT is happening now)
		simulator = PolicySimulator(policy)
		allowed, reason = simulator.evaluate(action, actor, runtime_ctx)

		# 4. Output Result
		_print_result(allowed, reason)

		if verbose or not allowed:
			_print_trace(policy, action, runtime_ctx, reason, len(applicable_obligations))

	except Exception as e:
		console.print(f'[bold red]Check failed:[/bold red] {e}')
		raise typer.Exit(1) from e


def why(
	resource: str = typer.Option(..., '--resource', '-r', help='The URN of the resource.'),
	action: str = typer.Option(None, '--action', '-a', help='Optional: The action being attempted.'),
	context: str = typer.Option(
		'{}', '--context', '-c', help='JSON string of runtime context variables (e.g. \'{"region": "US"}\').'
	),
):
	"""
	Explain the provenance and reasoning behind a policy decision.

	If --action is provided, it explains specifically why that action is allowed/denied.
	If not, it lists all active governing constraints and their sources (Contracts/Regulations).
	"""
	try:
		# 1. Parse Context
		try:
			runtime_ctx = json.loads(context)
		except json.JSONDecodeError:
			console.print('[bold red]Error:[/bold red] --context must be valid JSON.')
			raise typer.Exit(1) from None

		# 2. Resolve Policy
		config = load_config()
		loader = ObligationLoader(config)

		with console.status('[dim]Tracing policy lineage...[/dim]'):
			all_obligations = loader.load_all()
			if not all_obligations:
				console.print('[yellow]No obligations found. Policy is open by default.[/yellow]')
				return

			# Inventory Lookup & Matching
			resource_tags = _load_resource_tags(resource)
			matcher = ResourceMatcher()
			applicable_obligations = [ob for ob in all_obligations if matcher.matches(resource, resource_tags, ob)]

			engine = ConflictResolutionEngine()
			policy = engine.resolve(resource, applicable_obligations)

		# 3. Analyze Traces
		if action:
			_explain_specific_action(policy, action, runtime_ctx)
		else:
			_explain_general_policy(policy, len(applicable_obligations))

	except Exception as e:
		console.print(f'[bold red]Trace failed:[/bold red] {e}')
		raise typer.Exit(1) from e


# ==============================================================================
# "Why" Logic Helpers
# ==============================================================================


def _explain_specific_action(policy: ResolvedPolicy, action: str, context: dict[str, Any]):
	"""
	Simulates the check, finds the blocking constraint, and prints the
	specific ConflictTrace responsible for the denial.
	"""
	simulator = PolicySimulator(policy)  # Reusing the simulator class from check.py
	allowed, fail_reason_text = simulator.evaluate(action, 'audit', context)

	console.print(
		f"\nAnalysis for action [bold cyan]'{action}'[/bold cyan] on [bold cyan]{policy.resource_urn}[/bold cyan]:"
	)

	if allowed:
		console.print(
			Panel(
				'✅ [bold green]Action Allowed[/bold green]\n'
				'No blocking obligations were found for this specific context.',
				border_style='green',
			)
		)
		# Even if allowed, show what rules apply
		console.print('\n[dim]Governing policies that were checked:[/dim]')
		_explain_general_policy(policy, len(policy.contributing_obligation_ids))
		return

	# If Denied, find the specific trace
	trace: ConflictTrace | None = None

	# Heuristic matching of failure reason text to policy sections
	act = action.lower()

	# 1. Check AI Blockers
	if policy.ai_rules:
		if 'train' in act and not policy.ai_rules.training_allowed:
			trace = policy.ai_rules.reason
		elif 'fine' in act and not policy.ai_rules.fine_tuning_allowed:
			trace = policy.ai_rules.reason
		elif 'rag' in act and not policy.ai_rules.rag_allowed:
			trace = policy.ai_rules.reason

	# 2. Check Geo Blockers
	if not trace and policy.geofencing:
		region = str(context.get('region', '')).upper()
		if policy.geofencing.is_global_ban:
			trace = policy.geofencing.reason
		elif region and region in policy.geofencing.blocked_regions:
			trace = policy.geofencing.reason
		elif region and policy.geofencing.allowed_regions and region not in policy.geofencing.allowed_regions:
			trace = policy.geofencing.reason

	# 3. Check Purpose Blockers
	if not trace and policy.purpose:
		purpose = str(context.get('purpose', '')).upper()
		if purpose and purpose in policy.purpose.denied_purposes:
			trace = policy.purpose.reason
		elif purpose and policy.purpose.allowed_purposes and purpose not in policy.purpose.allowed_purposes:
			trace = policy.purpose.reason

	# 4. Check Retention Blockers (Expiration)
	if not trace and policy.retention and not policy.retention.is_indefinite:
		# Check if "expired" is in the reason text returned by simulator
		if 'expired' in fail_reason_text.lower():
			trace = policy.retention.reason

	# 5. Render the Evidence
	if trace:
		_print_trace_evidence(trace, '⛔ BLOCKING SOURCE')
	else:
		# Fallback if exact trace mapping fails logic
		console.print(f'[bold red]Denied:[/bold red] {fail_reason_text}')


def _explain_general_policy(policy: ResolvedPolicy, matched_count: int):
	"""
	Lists all active constraints and their sources.
	"""
	console.print(f'[dim]Matched {matched_count} obligations based on inventory tags/patterns.[/dim]')

	if not (policy.retention or policy.geofencing or policy.ai_rules or policy.purpose or policy.privacy):
		console.print('[dim]No active constraints on this resource.[/dim]')
		return

	table = Table(title='Active Governance Constraints', show_header=True)
	table.add_column('Domain', style='cyan')
	table.add_column('Winning Source', style='bold magenta')
	table.add_column('Reasoning', style='white')

	if policy.retention:
		t = policy.retention.reason
		table.add_row('Retention', t.winning_source_id, t.description)

	if policy.geofencing:
		t = policy.geofencing.reason
		table.add_row('Geofencing', t.winning_source_id, t.description)

	if policy.ai_rules:
		t = policy.ai_rules.reason
		table.add_row('AI/ML Usage', t.winning_source_id, t.description)

	if policy.purpose:
		t = policy.purpose.reason
		table.add_row('Purpose Limit', t.winning_source_id, t.description)

	if policy.privacy:
		t = policy.privacy.reason
		table.add_row('Privacy Method', t.winning_source_id, t.description)

	console.print(table)


def _print_trace_evidence(trace: ConflictTrace, title: str):
	"""
	Renders a ConflictTrace as a 'Legal Evidence' card.
	"""
	grid = Table.grid(expand=True)
	grid.add_column()
	grid.add_column(justify='right')

	grid.add_row(f'[bold red]{title}[/bold red]', f'[dim]Obligation ID: {trace.winning_obligation_id}[/dim]')

	details = f"""
    [bold]Source:[/bold] {trace.winning_source_id}
    [bold]Logic:[/bold]  {trace.description}
    """

	console.print(Panel(Group(grid, details), border_style='red'))


# ==============================================================================
# Policy Simulator Logic
# ==============================================================================


class PolicySimulator:
	"""
	Simulates the logic of an enforcement agent (like OPA or the SDK).
	It maps abstract constraints (ResolvedPolicy) to concrete Actions.
	"""

	def __init__(self, policy: ResolvedPolicy):
		self.policy = policy

	def evaluate(self, action: str, actor_id: str, context: dict[str, Any]) -> tuple[bool, str]:
		"""
		Returns (is_allowed, reason).
		"""
		# 1. AI Rules Check
		# Maps actions like "train", "fine_tune", "rag" to AI constraints.
		if self.policy.ai_rules:
			ai = self.policy.ai_rules
			act = action.lower()

			if 'train' in act and not ai.training_allowed:
				return False, f"AI Training is forbidden by obligation '{ai.reason.winning_source_id}'."

			if ('fine_tune' in act or 'finetune' in act) and not ai.fine_tuning_allowed:
				return False, f"Fine-tuning is forbidden by obligation '{ai.reason.winning_source_id}'."

			if 'rag' in act and not ai.rag_allowed:
				return False, f"RAG usage is forbidden by obligation '{ai.reason.winning_source_id}'."

		# 2. Geofencing Check
		# Looks for 'region', 'location', or 'geo' in context.
		if self.policy.geofencing:
			geo = self.policy.geofencing

			# Extract region from context (case-insensitive key search)
			current_region = None
			for key in ['region', 'location', 'geo_region', 'country']:
				if key in context:
					current_region = str(context[key]).upper()
					break

			if current_region:
				# A. Global Ban
				if geo.is_global_ban:
					return False, f"Data Access is globally banned by '{geo.reason.winning_source_id}'."

				# B. Blocked List
				if current_region in geo.blocked_regions:
					return (
						False,
						f"Region '{current_region}' is explicitly blocked by '{geo.reason.winning_source_id}'.",
					)

				# C. Allowed List (Strict Residency)
				# If an allowed list exists, you MUST be in it.
				if geo.allowed_regions and current_region not in geo.allowed_regions:
					return (
						False,
						f"Region '{current_region}' is not in the allowed list "
						f"defined by '{geo.reason.winning_source_id}'.",
					)

		# 3. Purpose Check
		if self.policy.purpose:
			pur = self.policy.purpose
			current_purpose = str(context.get('purpose', '')).upper()

			if current_purpose:
				if current_purpose in pur.denied_purposes:
					return (
						False,
						f"Purpose '{current_purpose}' is forbidden by obligation '{pur.reason.winning_source_id}'.",
					)

				if pur.allowed_purposes and current_purpose not in pur.allowed_purposes:
					return (
						False,
						f"Purpose '{current_purpose}' is not in the allowed list "
						f"defined by '{pur.reason.winning_source_id}'.",
					)

		# 4. Privacy Check (Informational, usually doesn't block unless required)
		if self.policy.privacy:
			# If the action suggests reading raw data, we can flag it.
			# For now, we allow it but append the privacy requirement to the reason.
			method_name = self.policy.privacy.method.name
			return True, f'Allowed, subject to privacy transformation: {method_name}'

		# 5. Retention Check
		if self.policy.retention:
			ret = self.policy.retention
			if ret.is_indefinite:
				# Legal Hold active -> Data is preserved regardless of age.
				# However, if the action was 'delete', we might want to block it.
				if 'delete' in action.lower():
					return False, f"Deletion blocked by Legal Hold (Source: '{ret.reason.winning_source_id}')."
			else:
				# Look for creation date in context
				created_val = None
				for k in ['created_at', 'creation_date', 'date']:
					if k in context:
						created_val = context[k]
						break

				if created_val:
					try:
						# Try ISO format
						if isinstance(created_val, str):
							dt = datetime.fromisoformat(created_val)
						else:
							# Assume datetime object if somehow passed (unlikely in CLI)
							dt = created_val

						# Ensure UTC for math
						if dt.tzinfo is None:
							dt = dt.replace(tzinfo=timezone.utc)

						age = datetime.now(timezone.utc) - dt

						if age > ret.duration:
							return (
								False,
								f'Data is expired (Age: {age.days}d > Retention: {ret.duration.days}d). '
								f"Obligation: '{ret.reason.winning_source_id}'.",
							)
					except ValueError:
						# Malformed date, warn via return message but allow (Fail Open logic for CLI)
						return True, 'Retention check skipped (Invalid date format in context).'
				else:
					# Metadata missing
					# We return True but modify reason to indicate skip
					return True, "Retention check skipped (Missing 'created_at' in context)."

		# Default: Allow
		return True, 'No blocking policies triggered.'


# ==============================================================================
# UI Helpers
# ==============================================================================


def _print_result(allowed: bool, reason: str):
	if allowed:
		console.print(Panel(f'[bold green]✅ ALLOWED[/bold green]\n[dim]{reason}[/dim]', border_style='green'))
	else:
		console.print(Panel(f'[bold red]❌ DENIED[/bold red]\n[white]{reason}[/white]', border_style='red'))


def _print_trace(policy: ResolvedPolicy, action: str, context: dict, final_reason: str, matched_count: int):
	"""
	Prints a tree view of what was checked.
	"""
	tree = Tree('[bold]Decision Trace[/bold]')

	# Context Node
	ctx_node = tree.add('Context Evaluated')
	ctx_node.add(f'Action: [cyan]{action}[/cyan]')
	for k, v in context.items():
		ctx_node.add(f'{k}: [cyan]{v}[/cyan]')

	# Policy Node
	pol_node = tree.add(f'Policy: [cyan]{policy.resource_urn}[/cyan]')
	pol_node.add(f'[dim](Derived from {matched_count} applicable obligations)[/dim]')

	if policy.ai_rules:
		ai_node = pol_node.add('AI Rules')
		if 'train' in action.lower() and not policy.ai_rules.training_allowed:
			ai_node.add(f'[red]Training Blocked[/red] (Source: {policy.ai_rules.reason.winning_source_id})')
		else:
			ai_node.add('[green]Pass[/green]')

	if policy.geofencing:
		geo_node = pol_node.add('Geofencing')
		region = context.get('region', context.get('location', 'Unknown')).upper()
		if region != 'UNKNOWN':
			if region in policy.geofencing.blocked_regions:
				geo_node.add(
					f'[red]Region {region} Blocked[/red] (Source: {policy.geofencing.reason.winning_source_id})'
				)
			elif policy.geofencing.allowed_regions and region not in policy.geofencing.allowed_regions:
				geo_node.add(
					f'[red]Region {region} Not Allowed[/red] (Source: {policy.geofencing.reason.winning_source_id})'
				)
			else:
				geo_node.add(f'Region {region}: [green]Pass[/green]')
		else:
			geo_node.add('[dim]Region not provided in context, skipped check.[/dim]')

	if policy.purpose:
		pur_node = pol_node.add('Purpose')
		purpose = context.get('purpose', 'Unknown').upper()
		if purpose != 'UNKNOWN':
			if purpose in policy.purpose.denied_purposes:
				pur_node.add(
					f'[red]Purpose {purpose} Blocked[/red] (Source: {policy.purpose.reason.winning_source_id})'
				)
			elif policy.purpose.allowed_purposes and purpose not in policy.purpose.allowed_purposes:
				pur_node.add(
					f'[red]Purpose {purpose} Not Whitelisted[/red] (Source: {policy.purpose.reason.winning_source_id})'
				)
			else:
				pur_node.add(f'Purpose {purpose}: [green]Pass[/green]')
		else:
			pur_node.add('[dim]Purpose not provided in context.[/dim]')

	if policy.retention:
		ret_node = pol_node.add('Retention')
		if policy.retention.is_indefinite:
			ret_node.add(f'[yellow]Legal Hold Active[/yellow] (Source: {policy.retention.reason.winning_source_id})')
		elif 'expired' in final_reason.lower():
			ret_node.add(f'[red]Data Expired[/red] (Source: {policy.retention.reason.winning_source_id})')
		else:
			ret_node.add(f'Duration: {policy.retention.duration}. [green]Valid[/green]')

	if policy.privacy:
		pol_node.add(f'Privacy: [magenta]{policy.privacy.method.name}[/magenta] enforced.')

	console.print('\n')
	console.print(tree)

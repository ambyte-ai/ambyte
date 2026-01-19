from datetime import datetime

import typer
from ambyte_cli.config import load_config
from ambyte_cli.services.api_client import CloudApiClient
from ambyte_cli.services.audit_verifier import AuditVerifier
from ambyte_cli.ui.console import console
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(help='Verify cryptographic integrity of audit logs.')


@app.command(name='verify')
def verify_log(
	log_id: str = typer.Argument(..., help='The UUID of the audit log to verify.'),
	public_key: str = typer.Option(
		None,
		'--key',
		'-k',
		envvar='AMBYTE_SYSTEM_PUBLIC_KEY',
		help='The System Public Key (Hex) to verify the block signature. Defaults to env var.',
	),
	verbose: bool = typer.Option(False, '--verbose', '-v', help='Show detailed Merkle path calculation.'),
):
	"""
	Cryptographically verify an Audit Log Entry.

	Checks:
	1. Content Integrity (Re-hashing the log entry)
	2. Inclusion Integrity (Merkle Tree Path verification)
	3. Authority Integrity (Block Signature verification)
	"""
	if not public_key:
		console.print('[error]Missing Public Key.[/error] Please provide --key or set AMBYTE_SYSTEM_PUBLIC_KEY.')
		raise typer.Exit(1)

	try:
		config = load_config()
		client = CloudApiClient(config)

		with console.status(f'[info]Fetching proof for {log_id}...[/info]'):
			proof_data = client.get_audit_proof(log_id)

		entry = proof_data['entry']
		header = proof_data['block_header']
		siblings = proof_data['merkle_siblings']

		# ======================================================================
		# STEP 1: Content Integrity (Local Hash)
		# ======================================================================
		server_hash = entry['entry_hash']
		local_hash = AuditVerifier.compute_local_entry_hash(entry)

		if server_hash != local_hash:
			_print_fail(
				'Content Tampering Detected',
				f'The log content does not match its hash.\nServer Hash: {server_hash}\nLocal Hash:  {local_hash}',
			)
			raise typer.Exit(1)

		step1_res = Text('✅ Content Integrity Verified (Local hash matches record)', style='green')

		# ======================================================================
		# STEP 2: Inclusion Integrity (Merkle)
		# ======================================================================
		is_merkle_valid = AuditVerifier.verify_merkle_path(
			target_hash=local_hash, siblings=siblings, expected_root=header['merkle_root']
		)

		if not is_merkle_valid:
			_print_fail(
				'Merkle Proof Failed',
				'The Merkle path provided does not resolve to the Block Root.\n'
				'This log entry is NOT part of the claimed block.',
			)
			raise typer.Exit(1)

		step2_res = Text(f'✅ Inclusion Verified (Path length: {len(siblings)})', style='green')

		# ======================================================================
		# STEP 3: Authority Integrity (Signature)
		# ======================================================================
		is_sig_valid = AuditVerifier.verify_block_signature(header, public_key)

		if not is_sig_valid:
			_print_fail(
				'Invalid Block Signature',
				'The Block Header signature failed verification against the provided Public Key.\n'
				'The block may be forged or the key is incorrect.',
			)
			raise typer.Exit(1)

		step3_res = Text('✅ Block Signature Verified', style='green')

		# ======================================================================
		# SUCCESS OUTPUT
		# ======================================================================

		grid = Table.grid(expand=True)
		grid.add_column()
		grid.add_row(step1_res)
		grid.add_row(step2_res)
		grid.add_row(step3_res)

		details = Table(show_header=False, box=None)
		details.add_row('Block Index', str(header['sequence_index']))
		details.add_row('Block Time', header['timestamp_end'])
		details.add_row('Log Decision', f'[{"green" if entry["decision"] == "ALLOW" else "red"}]{entry["decision"]}[/]')
		details.add_row('Actor', entry['actor']['id'])

		console.print(
			Panel(
				Group(
					Text('AUTHENTIC AUDIT LOG', style='bold green justify-center'), Text(''), grid, Text(''), details
				),
				border_style='green',
				title='Verification Success',
			)
		)

		if verbose:
			console.print('\n[dim]Merkle Root:[/dim]', header['merkle_root'])
			console.print('[dim]Signature:[/dim]', header['signature'][:32] + '...')

	except Exception as e:
		console.print(f'[error]Verification Error:[/error] {e}')
		raise typer.Exit(1) from e


def _print_fail(title: str, reason: str):
	console.print(Panel(f'[bold]{title}[/bold]\n\n{reason}', border_style='red', title='❌ TAMPER DETECTED'))


@app.command(name='list')
def list_logs(
	limit: int = typer.Option(20, '--limit', '-n', help='Number of logs to show.'),
	actor: str = typer.Option(None, '--actor', help='Filter by Actor ID.'),
	resource: str = typer.Option(None, '--resource', help='Filter by Resource URN.'),
):
	"""
	List recent audit logs to find IDs for verification.
	"""
	try:
		config = load_config()
		client = CloudApiClient(config)

		with console.status('[info]Fetching audit logs...[/info]'):
			logs = client.list_audit_logs(limit=limit, actor=actor, resource=resource)

		if not logs:
			console.print('[yellow]No audit logs found matching criteria.[/yellow]')
			return

		table = Table(title=f'Recent Audit Logs ({len(logs)})', show_header=True, header_style='bold cyan')
		table.add_column('Log ID (UUID)', style='dim')
		table.add_column('Time', width=20)
		table.add_column('Decision')
		table.add_column('Actor')
		table.add_column('Action')
		table.add_column('Status', justify='center')

		for log in logs:
			# Parse time
			dt = datetime.fromisoformat(log['timestamp'])
			time_str = dt.strftime('%Y-%m-%d %H:%M:%S')

			# Colorize decision
			decision_style = 'green' if log['decision'] == 'ALLOW' else 'red'
			decision_txt = f'[{decision_style}]{log["decision"]}[/{decision_style}]'

			# Check sealed status
			is_sealed = log.get('block_id') is not None
			status_icon = '🔒 Sealed' if is_sealed else '[yellow]⏳ Buffered[/yellow]'

			actor_id = log.get('actor_id', 'unknown')

			table.add_row(log['id'], time_str, decision_txt, actor_id, log['action'], status_icon)

		console.print(table)
		console.print(
			'\n[dim]Run [bold]ambyte audit verify <Log ID>[/bold] to cryptographically prove integrity.[/dim]'
		)

	except Exception as e:
		console.print(f'[error]Failed to list logs:[/error] {e}')
		raise typer.Exit(1) from e

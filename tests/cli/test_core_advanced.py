import json
import os
import shutil
import textwrap
from datetime import timedelta
from unittest import mock

import pytest
from ambyte_cli.main import app
from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	Obligation,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES: Workspace Setup
# ==============================================================================


@pytest.fixture
def workspace(tmp_path):
	"""
	Sets up a temporary Ambyte workspace with config and inventory.
	"""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)

	# 1. Initialize
	runner.invoke(app, ['init', '--yes'])

	# 2. Clean up sample policies to ensure test isolation
	# We remove the whole directory and recreate it to ensure gdpr_sample.yaml is gone
	policies_dir = tmp_path / 'policies'
	if policies_dir.exists():
		shutil.rmtree(policies_dir)
	policies_dir.mkdir()

	# 3. Setup Inventory (resources.yaml)
	(tmp_path / 'resources.yaml').write_text(
		textwrap.dedent("""
        resources:
          - urn: "urn:snowflake:prod:sensitive"
            tags: 
              sensitivity: "high"
              env: "prod"
        
          - urn: "urn:s3:logs"
            tags:
              sensitivity: "low"
        """),
		encoding='utf-8',
	)

	# 4. Setup a Policy on disk (Current State)
	# Retention: 30 days for high sensitivity
	(tmp_path / 'policies' / 'retention.yaml').write_text(
		textwrap.dedent("""
        id: retention-30d
        title: 30 Day Limit
        provenance: {source_id: "GDPR", document_type: "REG"}
        enforcement_level: "BLOCKING"
        target:
          match_tags: {sensitivity: "high"}
        constraint:
          type: "RETENTION"
          duration: "30d"
          trigger: "CREATION_DATE"
        """),
		encoding='utf-8',
	)

	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


def make_obligation(slug: str, duration_days: int) -> Obligation:
	"""Helper to create obligation objects for mocking Git history."""
	return Obligation(
		id=slug,
		title='Historical Policy',
		description='...',
		provenance=SourceProvenance(source_id='HIST', document_type='OLD'),
		enforcement_level=EnforcementLevel.BLOCKING,
		target={'match_tags': {'sensitivity': 'high'}},  # Matches our test resource
		retention=RetentionRule(
			duration=timedelta(days=duration_days),
			trigger=RetentionTrigger.CREATION_DATE,
		),
	)


# ==============================================================================
# TESTS: 'resolve' Command
# ==============================================================================


def test_resolve_inventory_match(workspace):
	"""
	Scenario: User asks to resolve a URN that exists in resources.yaml.
	The CLI should look up tags (sensitivity: high) and match the policy.
	"""
	result = runner.invoke(app, ['resolve', 'urn:snowflake:prod:sensitive'])

	if result.exit_code != 0:
		print(result.stdout)  # Helper for debugging if it fails

	assert result.exit_code == 0
	# Check that it found tags
	assert 'Found tags for urn:snowflake:prod:sensitive' in result.stdout
	assert "'sensitivity': 'high'" in result.stdout
	# Check that it matched the policy
	assert 'Matched 1/1 obligations' in result.stdout
	# Check Output Table
	assert 'Retention Policy' in result.stdout
	assert '30 days, 0:00:00' in result.stdout
	assert 'retention-30d' in result.stdout


def test_resolve_inventory_miss(workspace):
	"""
	Scenario: URN is not in resources.yaml.
	Should warn about empty context and likely match nothing (unless global).
	"""
	result = runner.invoke(app, ['resolve', 'urn:unknown:resource'])

	assert result.exit_code == 0
	assert 'No tags found in inventory' in result.stdout
	# Since our policy requires 'sensitivity: high', this should match 0
	assert 'Matched 0/1 obligations' in result.stdout
	assert 'No Retention rules active' in result.stdout


def test_resolve_json_output(workspace):
	"""
	Scenario: --json flag should print raw JSON of ResolvedPolicy.
	"""
	result = runner.invoke(app, ['resolve', 'urn:snowflake:prod:sensitive', '--json'])

	assert result.exit_code == 0
	data = json.loads(result.stdout)

	assert data['resource_urn'] == 'urn:snowflake:prod:sensitive'
	assert data['retention']['duration'] == 'P30D'  # ISO duration format
	assert 'retention-30d' in data['contributing_obligation_ids']


def test_resolve_no_obligations(workspace):
	"""
	Scenario: Policies directory is empty.
	"""
	os.remove(workspace / 'policies' / 'retention.yaml')

	result = runner.invoke(app, ['resolve', 'urn:test'])

	assert result.exit_code == 1
	assert 'No obligations found' in result.stdout


# ==============================================================================
# TESTS: 'diff' Command
# ==============================================================================


def test_diff_risk_decrease(workspace):
	"""
	Scenario: Current state is 30d (Restrictive).
	Historical state was 365d (Permissive).
	Diff should show "Risk Profile Decreased" (stricter).
	"""
	# Mock the Git loader to return the "Old" state (365 days)
	with mock.patch('ambyte_cli.commands.core.GitHistoryLoader') as MockLoader:
		loader_instance = MockLoader.return_value
		loader_instance.load_at_revision.return_value = [make_obligation('retention-30d', 365)]

		# Run diff against "urn:snowflake:prod:sensitive" (which has high sensitivity tags)
		result = runner.invoke(
			app,
			[
				'diff',
				'--reference',
				'HEAD~1',
				'--resource',
				'urn:snowflake:prod:sensitive',
			],
			env={'COLUMNS': '160'},
		)

	assert result.exit_code == 0
	assert 'Diff vs HEAD~1' in result.stdout
	assert 'Risk Profile Decreased' in result.stdout
	assert 'Retention duration changed' in result.stdout
	# Verify old vs new in table
	assert '365 days' in result.stdout
	assert '30 days' in result.stdout


def test_diff_risk_increase(workspace):
	"""
	Scenario: Current state is 30d.
	Historical state was 1d (Very Strict).
	Going from 1d -> 30d is "Risk Profile INCREASED" (Permissive change).
	"""
	with mock.patch('ambyte_cli.commands.core.GitHistoryLoader') as MockLoader:
		loader_instance = MockLoader.return_value
		loader_instance.load_at_revision.return_value = [make_obligation('retention-30d', 1)]

		result = runner.invoke(app, ['diff', '--resource', 'urn:snowflake:prod:sensitive'])

	assert result.exit_code == 0
	assert 'Risk Profile INCREASED' in result.stdout
	assert '🔓 Looser' in result.stdout


def test_diff_no_changes(workspace):
	"""
	Scenario: Historical state matches current state exactly.
	"""
	with mock.patch('ambyte_cli.commands.core.GitHistoryLoader') as MockLoader:
		loader_instance = MockLoader.return_value
		# Match the 30d on disk
		loader_instance.load_at_revision.return_value = [make_obligation('retention-30d', 30)]

		result = runner.invoke(app, ['diff', '--resource', 'urn:snowflake:prod:sensitive'])

	assert result.exit_code == 0
	assert 'No semantic policy changes detected' in result.stdout


def test_diff_markdown_output(workspace):
	"""
	Scenario: --md flag produces Markdown table.
	"""
	with mock.patch('ambyte_cli.commands.core.GitHistoryLoader') as MockLoader:
		loader_instance = MockLoader.return_value
		loader_instance.load_at_revision.return_value = [make_obligation('retention-30d', 365)]

		result = runner.invoke(app, ['diff', '--resource', 'urn:snowflake:prod:sensitive', '--md'])

	assert result.exit_code == 0
	assert '### 📋 Policy Diff Report' in result.stdout
	assert '| Category | Impact |' in result.stdout  # Markdown table header


def test_diff_git_error(workspace):
	"""
	Scenario: Git command fails (e.g. invalid revision).
	"""
	with mock.patch('ambyte_cli.commands.core.GitHistoryLoader') as MockLoader:
		loader_instance = MockLoader.return_value
		loader_instance.load_at_revision.side_effect = ValueError("Git revision 'invalid' not found")

		result = runner.invoke(app, ['diff', '--reference', 'invalid'])

	assert result.exit_code == 1
	assert 'Git Error' in result.stdout
	assert "Git revision 'invalid' not found" in result.stdout

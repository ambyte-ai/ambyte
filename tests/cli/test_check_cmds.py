import json
import os
import textwrap
from datetime import datetime, timedelta, timezone

import pytest
from ambyte_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES: Workspace Setup
# ==============================================================================


@pytest.fixture
def workspace(tmp_path):
	"""
	Sets up a temporary Ambyte workspace with:
	1. config.yaml
	2. resources.yaml (Inventory with Tags)
	3. policies/complex.yaml (A policy covering all domains)
	"""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)

	# 1. Initialize
	runner.invoke(app, ['init', '--yes'])

	# 2. Inventory: Define a tagged resource
	(tmp_path / 'resources' / 'resources.yaml').write_text(
		textwrap.dedent("""
        resources:
          - urn: "urn:snowflake:sensitive:data"
            platform: "snowflake"
            tags: 
              sensitivity: "high"
              dept: "finance"
    
          - urn: "urn:s3:public:logs"
            platform: "aws"
            tags:
              sensitivity: "low"
        """),
		encoding='utf-8',
	)

	# 3. Policy: A comprehensive rule targeting "high" sensitivity
	#    - Blocks Geo: CN, RU
	#    - Blocks AI Training
	#    - Blocks Purpose: MARKETING
	#    - Retention: 30 Days
	(tmp_path / 'policies' / 'complex.yaml').write_text(
		textwrap.dedent("""
        id: complex-policy-1
        title: High Sensitivity Controls
        provenance: {source_id: "CORP-SEC-01", document_type: "POLICY"}
        enforcement_level: "BLOCKING"
        
        target:
          match_tags:
            sensitivity: "high"

        # NOTE: In valid Ambyte YAML, we usually have separate files or OneOf constraints.
        # However, the loader allows loading multiple files. 
        # For this test, we will create separate files to layer the constraints onto the same resource 
        # so the Resolution Engine combines them into one ResolvedPolicy.
        constraint:
          type: "GEOFENCING"
          denied_regions: ["CN", "RU"]
        """),
		encoding='utf-8',
	)

	(tmp_path / 'policies' / 'ai_rules.yaml').write_text(
		textwrap.dedent("""
        id: ai-policy-1
        title: No AI Training
        provenance: {source_id: "AI-ETHICS", document_type: "STD"}
        enforcement_level: "BLOCKING"
        target:
          match_tags: {sensitivity: "high"}
        constraint:
          type: "AI_MODEL_CONSTRAINT"
          training_allowed: false
          fine_tuning_allowed: true
        """),
		encoding='utf-8',
	)

	(tmp_path / 'policies' / 'retention.yaml').write_text(
		textwrap.dedent("""
        id: ret-policy-1
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

	(tmp_path / 'policies' / 'purpose.yaml').write_text(
		textwrap.dedent("""
        id: purp-policy-1
        title: No Spam
        provenance: {source_id: "CONSENT", document_type: "USER"}
        enforcement_level: "BLOCKING"
        target:
          match_tags: {sensitivity: "high"}
        constraint:
          type: "PURPOSE_RESTRICTION"
          denied_purposes: ["MARKETING"]
        """),
		encoding='utf-8',
	)

	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


# ==============================================================================
# TESTS: Command 'check'
# ==============================================================================


def test_check_basic_allow(workspace):
	"""
	Scenario: Accessing a resource that has matching policies, but the context implies SAFETY.
	Resource: urn:snowflake:sensitive:data (Matches "high" sensitivity)
	Context: Region US (Allowed), Action Read (Allowed)
	"""
	result = runner.invoke(
		app,
		[
			'check',
			'--resource',
			'urn:snowflake:sensitive:data',
			'--action',
			'read',
			'--context',
			'{"region": "US"}',
			'--actor',
			'data_scientist',
		],
	)

	assert result.exit_code == 0
	assert '✅ ALLOWED' in result.stdout
	assert 'Applied tags from inventory' in result.stdout


def test_check_geo_deny(workspace):
	"""
	Scenario: Accessing from a Blocked Region (CN).
	"""
	result = runner.invoke(
		app,
		['check', '--resource', 'urn:snowflake:sensitive:data', '--action', 'query', '--context', '{"region": "CN"}'],
	)

	assert result.exit_code == 0  # Command runs successfully
	assert '❌ DENIED' in result.stdout
	assert "Region 'CN' is explicitly blocked" in result.stdout
	# Check that trace is printed on denial
	assert 'Decision Trace' in result.stdout
	assert 'Geofencing' in result.stdout


def test_check_ai_deny(workspace):
	"""
	Scenario: Attempting AI Training on protected data.
	"""
	result = runner.invoke(
		app, ['check', '--resource', 'urn:snowflake:sensitive:data', '--action', 'train_model', '--context', '{}']
	)

	assert '❌ DENIED' in result.stdout
	assert 'AI Training is forbidden' in result.stdout
	assert 'AI Rules' in result.stdout


def test_check_retention_expired(workspace):
	"""
	Scenario: Data is older than 30 days.
	"""
	# Calculate a date 40 days ago
	old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()

	# We must properly escape quotes for command line args in some shells,
	# but CliRunner handles list args directly.
	context_str = json.dumps({'created_at': old_date})

	result = runner.invoke(
		app, ['check', '--resource', 'urn:snowflake:sensitive:data', '--action', 'read', '--context', context_str]
	)

	assert '❌ DENIED' in result.stdout
	assert 'Data is expired' in result.stdout
	assert 'Retention' in result.stdout


def test_check_retention_valid(workspace):
	"""
	Scenario: Data is new (1 day old). Should allow.
	"""
	new_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
	context_str = json.dumps({'created_at': new_date, 'region': 'US'})  # Add region to pass Geo check

	result = runner.invoke(
		app, ['check', '--resource', 'urn:snowflake:sensitive:data', '--action', 'read', '--context', context_str]
	)

	assert '✅ ALLOWED' in result.stdout


def test_check_purpose_deny(workspace):
	"""
	Scenario: Using data for MARKETING (Denied).
	"""
	result = runner.invoke(
		app,
		[
			'check',
			'--resource',
			'urn:snowflake:sensitive:data',
			'--action',
			'email_blast',
			'--context',
			'{"purpose": "MARKETING", "region": "US"}',
		],
	)

	assert '❌ DENIED' in result.stdout
	assert "Purpose 'MARKETING' is forbidden" in result.stdout


def test_check_unmatched_resource_allow(workspace):
	"""
	Scenario: Resource 'urn:s3:public:logs' has 'sensitivity: low'.
	Our policies target 'sensitivity: high'.
	Therefore, no policies apply -> Default Allow.
	"""
	result = runner.invoke(app, ['check', '--resource', 'urn:s3:public:logs', '--action', 'delete'])

	assert '✅ ALLOWED' in result.stdout
	assert 'No blocking policies triggered' in result.stdout


def test_check_invalid_json_context(workspace):
	"""
	Scenario: User passes bad JSON. Should error gracefully.
	"""
	result = runner.invoke(app, ['check', '--resource', 'urn:test', '--action', 'read', '--context', '{bad_json'])

	assert result.exit_code == 1
	assert 'Error: --context must be valid JSON' in result.stdout


def test_check_verbose_mode(workspace):
	"""
	Scenario: --verbose should print the Decision Trace even on ALLOW.
	"""
	result = runner.invoke(
		app,
		[
			'check',
			'--resource',
			'urn:snowflake:sensitive:data',
			'--action',
			'read',
			'--context',
			'{"region": "US"}',
			'--verbose',
		],
	)

	assert '✅ ALLOWED' in result.stdout
	# Verbose confirms trace is printed
	assert 'Decision Trace' in result.stdout
	assert 'Context Evaluated' in result.stdout


# ==============================================================================
# TESTS: Command 'why'
# ==============================================================================


def test_why_general_report(workspace):
	"""
	Scenario: 'ambyte why' without action shows all active constraints.
	"""
	result = runner.invoke(app, ['why', '--resource', 'urn:snowflake:sensitive:data'])

	assert result.exit_code == 0
	assert 'Active Governance Constraints' in result.stdout

	# Check that it lists the domains we defined
	assert 'Retention' in result.stdout
	assert 'Geofencing' in result.stdout
	assert 'AI/ML Usage' in result.stdout
	assert 'Purpose Limit' in result.stdout

	# Check it identifies the sources
	assert 'GDPR' in result.stdout
	assert 'CORP-SEC-01' in result.stdout


def test_why_specific_action_blocked(workspace):
	"""
	Scenario: 'ambyte why --action train_model' should pinpoint the specific blocking rule.
	"""
	result = runner.invoke(app, ['why', '--resource', 'urn:snowflake:sensitive:data', '--action', 'train_model'])

	assert "Analysis for action 'train_model'" in result.stdout
	# Should show the blocking source card
	assert '⛔ BLOCKING SOURCE' in result.stdout
	assert 'Obligation ID: ai-policy-1' in result.stdout
	assert 'Source: AI-ETHICS' in result.stdout


def test_why_specific_action_allowed(workspace):
	"""
	Scenario: 'ambyte why --action read' should show Allowed and then the general policy.
	"""
	result = runner.invoke(
		app, ['why', '--resource', 'urn:snowflake:sensitive:data', '--action', 'read', '--context', '{"region": "US"}']
	)

	assert '✅ Action Allowed' in result.stdout
	assert 'Governing policies that were checked' in result.stdout
	# Should still list the active rules even if passed
	assert 'Active Governance Constraints' in result.stdout


def test_why_no_policies(workspace):
	"""
	Scenario: Checking a resource with no matching policies.
	"""
	result = runner.invoke(app, ['why', '--resource', 'urn:s3:public:logs'])

	assert 'No active constraints on this resource' in result.stdout


def test_why_invalid_json(workspace):
	result = runner.invoke(app, ['why', '--resource', 'r', '--context', 'bad'])
	assert result.exit_code == 1
	assert 'Error: --context must be valid JSON' in result.stdout


# ==============================================================================
# TESTS: Inventory & Loader Edge Cases
# ==============================================================================


def test_missing_inventory_handling(workspace):
	"""
	If resources.yaml is missing, commands should still work (matching only globals).
	"""
	# Delete inventory
	os.remove(workspace / 'resources' / 'resources.yaml')

	result = runner.invoke(app, ['check', '--resource', 'urn:snowflake:sensitive:data', '--action', 'read'])

	assert result.exit_code == 0
	assert 'No inventory tags found' in result.stdout

	# Since tags are missing, the "match_tags: {sensitivity: high}" policies won't match.
	# So it should be ALLOWED (Open by default).
	assert '✅ ALLOWED' in result.stdout
	assert 'No blocking policies triggered' in result.stdout


def test_no_obligations_defined(workspace):
	"""
	If no policies exist in policies/, allow everything.
	"""
	# Delete all policies
	import shutil

	shutil.rmtree(workspace / 'policies')
	(workspace / 'policies').mkdir()

	result = runner.invoke(app, ['check', '--resource', 'urn:any', '--action', 'any'])

	assert 'No obligations defined' in result.stdout
	assert '✅ ALLOWED' in result.stdout

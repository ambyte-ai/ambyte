import json
import os
import textwrap
from unittest import mock

import pytest
import yaml
from ambyte_cli.config import CONFIG_DIR_NAME
from ambyte_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def workspace(tmp_path):
	"""
	Sets up a full Ambyte workspace with policies and inventory.
	"""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)

	# 1. Init (scaffold)
	runner.invoke(app, ['init', '--yes'])

	# Create templates dir to satisfy PolicyCompilerService checks
	(tmp_path / 'templates').mkdir(exist_ok=True)

	# 2. Add Custom Policy (Retention)
	(tmp_path / 'policies' / 'retention.yaml').write_text(
		textwrap.dedent("""
            id: ret-1
            title: Keep 30 Days
            provenance: {source_id: "GDPR", document_type: "REG"}
            enforcement_level: "BLOCKING"
            target:
              include_patterns: ["*"]
            constraint:
              type: "RETENTION"
              duration: "30d"
              trigger: "CREATION_DATE"
        """),
		encoding='utf-8',
	)

	# 3. Add Custom Inventory
	(tmp_path / 'resources.yaml').write_text(
		textwrap.dedent("""
            resources:
              - urn: "urn:snowflake:prod:sales"
                tags: {env: "prod"}
                config: 
                  snowflake: {allowed_roles: ["ADMIN"]}
                  
              - urn: "arn:aws:s3:::data-lake"
                tags: {env: "prod"}
        """),
		encoding='utf-8',
	)

	try:
		yield tmp_path
	finally:
		os.chdir(old_cwd)


# ==============================================================================
# TESTS
# ==============================================================================


def test_build_local_target(workspace):
	"""
	Test generating the Python SDK Bundle (local_policies.json).
	"""
	with mock.patch('shutil.which', return_value=None):
		# Enable LOCAL target (default)
		result = runner.invoke(app, ['build'])

	if result.exit_code != 0:
		print(result.stdout)

	assert result.exit_code == 0
	assert 'Generating Local Policy Bundle... Done' in result.stdout

	# Verify Artifact
	dist = workspace / '.ambyte' / 'dist'
	bundle_path = dist / 'local_policies.json'
	assert bundle_path.exists()

	data = json.loads(bundle_path.read_text())

	# Check Structure
	assert 'metadata' in data
	assert 'policies' in data

	# Check Content
	assert len(data['policies']) == 2
	assert 'urn:snowflake:prod:sales' in data['policies']
	assert 'arn:aws:s3:::data-lake' in data['policies']

	# Check Policy Logic
	policy = data['policies']['urn:snowflake:prod:sales']
	assert policy['retention']['duration'] == 'P30D'  # ISO 8601 Duration


def test_build_snowflake_target(workspace):
	"""
	Test generating SQL artifacts.
	Requires updating config to include 'snowflake' target.
	"""
	# 1. Update Config to enable Snowflake using YAML parser (Robust)
	config_path = workspace / CONFIG_DIR_NAME / 'config.yaml'

	with open(config_path, encoding='utf-8') as f:
		conf_data = yaml.safe_load(f) or {}

	# Add snowflake target if missing
	if 'targets' not in conf_data:
		conf_data['targets'] = ['local']
	if 'snowflake' not in conf_data['targets']:
		conf_data['targets'].append('snowflake')

	with open(config_path, 'w', encoding='utf-8') as f:
		yaml.dump(conf_data, f)

	(workspace / 'policies' / 'privacy.yaml').write_text(
		textwrap.dedent("""
            id: priv-1
            title: Mask Sensitive Data
            provenance: {source_id: "TEST", document_type: "INT"}
            enforcement_level: "BLOCKING"
            target:
              include_patterns: ["*"]
            constraint:
              type: "PRIVACY_ENHANCEMENT"
              method: "PSEUDONYMIZATION"
        """),
		encoding='utf-8',
	)

	# 2. Mock Template Path logic
	tpl_dir = workspace / 'templates'
	(tpl_dir / 'masking.sql').write_text(
		'CREATE OR REPLACE MASKING POLICY {{ policy_name }} ...'
	)  # Simplified content checks
	(tpl_dir / 'row_access.sql').write_text('-- RAP SQL')

	# 3. Build (Mock git here too)
	with mock.patch('shutil.which', return_value=None):
		result = runner.invoke(app, ['build'])

	assert result.exit_code == 0
	assert 'Generating Snowflake SQL... Done' in result.stdout

	# 4. Verify
	sql_file = workspace / '.ambyte' / 'dist' / 'masking_policies.sql'
	assert sql_file.exists()

	content = sql_file.read_text()
	assert 'Resource: urn:snowflake:prod:sales' in content
	assert 'MASKING POLICY' in content


def test_build_iam_target(workspace):
	"""
	Test generating AWS IAM JSON.
	Update config -> Build -> Check output.
	"""
	# 1. Enable IAM using YAML parser (Robust)
	config_path = workspace / CONFIG_DIR_NAME / 'config.yaml'

	with open(config_path, encoding='utf-8') as f:
		conf_data = yaml.safe_load(f) or {}

	if 'aws_iam' not in conf_data.get('targets', []):
		# Just set targets directly to be safe
		conf_data['targets'] = ['local', 'aws_iam']

	with open(config_path, 'w', encoding='utf-8') as f:
		yaml.dump(conf_data, f)

	# 2. Update Inventory to target an IAM Role (Identity Policy) instead of a Bucket
	# The BucketPolicyGenerator (s3:::) ignores 'denied_regions', but IamPolicyBuilder (role) supports it.
	(workspace / 'resources.yaml').write_text(
		textwrap.dedent("""
            resources:
              - urn: "arn:aws:iam::123456789012:role/DataScientist"
                tags: {env: "prod"}
        """),
		encoding='utf-8',
	)

	# 3. Add a Geofencing Policy
	(workspace / 'policies' / 'geo.yaml').write_text(
		textwrap.dedent("""
            id: geo-1
            title: Restrict Regions
            provenance: {source_id: "GEO", document_type: "REG"}
            enforcement_level: "BLOCKING"
            target:
              include_patterns: ["*"]
            constraint:
              type: "GEOFENCING"
              denied_regions: ["CN", "RU"]
        """),
		encoding='utf-8',
	)

	# 4. Build (Mock git)
	with mock.patch('shutil.which', return_value=None):
		result = runner.invoke(app, ['build'])

	if result.exit_code != 0:
		print(result.stdout)
	assert result.exit_code == 0

	# 5. Verify Output
	# The file name is derived from the Role name: iam_DataScientist.json
	dist = workspace / '.ambyte' / 'dist'
	iam_file = dist / 'iam_role_DataScientist.json'

	assert iam_file.exists()
	content = json.loads(iam_file.read_text())

	assert content['Version'] == '2012-10-17'
	assert isinstance(content['Statement'], list)
	# This assertion should now pass because IamPolicyBuilder generates this specific SID
	assert any(s['Sid'] == 'AmbyteGeoBlockDeniedRegions' for s in content['Statement'])


def test_build_clean_flag(workspace):
	"""
	Verify --clean removes old artifacts.
	"""
	dist = workspace / '.ambyte' / 'dist'
	dist.mkdir(parents=True, exist_ok=True)

	# Create garbage file
	(dist / 'garbage.txt').write_text('trash')

	with mock.patch('shutil.which', return_value=None):
		result = runner.invoke(app, ['build', '--clean'])

	assert result.exit_code == 0
	assert not (dist / 'garbage.txt').exists()
	assert (dist / 'local_policies.json').exists()


def test_build_no_inventory_warning(workspace):
	"""
	If inventory is empty, it should warn and use default context.
	"""
	# Clear inventory (at root, where loader looks)
	(workspace / 'resources.yaml').write_text('resources: []')

	with mock.patch('shutil.which', return_value=None):
		result = runner.invoke(app, ['build'])

	assert result.exit_code == 0
	assert 'No resources found' in result.stdout
	assert 'Using default wildcard context' in result.stdout

	# Verify default resource was processed
	dist = workspace / '.ambyte' / 'dist'
	data = json.loads((dist / 'local_policies.json').read_text())
	assert 'urn:local:default' in data['policies']

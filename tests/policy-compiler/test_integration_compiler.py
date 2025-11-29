import json
from datetime import timedelta
from pathlib import Path

import pytest
from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)

from apps.policy_compiler.diff_engine.service import SemanticDiffEngine
from apps.policy_compiler.service import PolicyCompilerService

# ------------------------------------------------------------------------------
# Fixtures & Helpers
# ------------------------------------------------------------------------------


@pytest.fixture
def templates_dir(tmp_path: Path):
	"""
	Creates a temporary directory with a dummy Snowflake SQL template
	required by the PolicyCompilerService.
	"""
	sql_content = """
	-- {{ comment }}
	CREATE OR REPLACE MASKING POLICY {{ policy_name }} AS (val {{ input_type }}) RETURNS {{ input_type }} ->
      CASE
		WHEN current_role() IN ({% for role in allowed_roles %}'{{ role }}'{% if not loop.last %}, {% endif %}{% endfor %}) THEN val
		{% if method == 'HASH' %}
		ELSE sha2(val)
		{% else %}
		ELSE '***MASKED***'
		{% endif %}
      END;
	"""  # noqa: E501, E101
	d = tmp_path / 'sql_templates'
	d.mkdir()
	p = d / 'masking.sql'
	p.write_text(sql_content)
	return d


def make_provenance(source_id: str) -> SourceProvenance:
	return SourceProvenance(source_id=source_id, document_type='Contract', section_reference='1.0')


def make_retention_ob(id: str, days: int) -> Obligation:
	return Obligation(
		id=id,
		title=f'Retention {days} days',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		retention=RetentionRule(duration=timedelta(days=days), trigger=RetentionTrigger.CREATION_DATE),
	)


def make_geo_ob(id: str, allowed: list[str], denied: list[str]) -> Obligation:
	return Obligation(
		id=id,
		title=f'Geo Rule {id}',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		geofencing=GeofencingRule(allowed_regions=allowed, denied_regions=denied),
	)


def make_ai_ob(id: str, training_allowed: bool) -> Obligation:
	return Obligation(
		id=id,
		title=f'AI Rule {id}',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		ai_model=AiModelConstraint(training_allowed=training_allowed, attribution_text_required='Credit Ambyte'),
	)


# ------------------------------------------------------------------------------
# Integration Tests
# ------------------------------------------------------------------------------


def test_pipeline_snowflake_retention(templates_dir):
	"""
	Scenario:
	1. Two conflicting retention rules (Contract: 5 years, GDPR: 2 years).
	2. Compiler should resolve to 2 years (Strictest).
	3. Generator should produce valid Snowflake SQL masking policy.
	"""
	service = PolicyCompilerService(templates_path=templates_dir)

	# 1. Input: Conflicting Obligations
	obs = [
		make_retention_ob('MSA-001', days=365 * 5),  # 5 Years
		make_retention_ob('GDPR-001', days=365 * 2),  # 2 Years (Winner)
	]

	# 2. Compile
	result = service.compile(
		resource_urn='urn:snowflake:sales_db:customers:email',
		obligations=obs,
		target='snowflake',
		context={'input_type': 'STRING', 'allowed_roles': ['ADMIN', 'PII_READER']},
	)

	# 3. Verify Output
	assert isinstance(result, str)
	assert 'CREATE OR REPLACE MASKING POLICY ambyte_mask_email' in result
	assert 'sha2(val)' in result  # Checks default privacy method is HASH
	assert "'ADMIN', 'PII_READER'" in result
	# Ensure the comment mentions valid obligations were found
	assert 'Obligations: 2' in result


def test_pipeline_opa_geofencing():
	"""
	Scenario:
	1. Complex Geo Logic:
	   - Rule A allows: US, EU, CA
	   - Rule B allows: US, CA (Intersection shrinks scope)
	   - Rule C denies: CA (Explicit deny removes CA)
	2. Result should be: US only.
	3. Generator should produce OPA Data Bundle JSON.
	"""  # noqa: E101
	service = PolicyCompilerService()  # No templates needed for OPA

	obs = [
		make_geo_ob('Rule-A', allowed=['US', 'EU', 'CA'], denied=[]),
		make_geo_ob('Rule-B', allowed=['US', 'CA'], denied=[]),
		make_geo_ob('Rule-C', allowed=[], denied=['CA']),
	]

	# 2. Compile
	result = service.compile(resource_urn='urn:api:user_service', obligations=obs, target='opa')

	# 3. Verify Output
	assert isinstance(result, dict)
	assert result['resource_urn'] == 'urn:api:user_service'

	geo_data = result['geofencing']
	assert geo_data['allowed_regions'] == ['US']
	assert 'CA' in geo_data['blocked_regions']
	assert geo_data['is_global_ban'] is False


def test_pipeline_iam_ai_guardrails():
	"""
	Scenario:
	1. AI Restriction: Training is FORBIDDEN by one contract.
	2. Generator should produce AWS IAM Policy with explicit Deny on SageMaker.
	"""
	service = PolicyCompilerService()

	obs = [
		make_ai_ob('OpenAI-TOS', training_allowed=True),
		make_ai_ob('Enterprise-MSA', training_allowed=False),  # Winner (Poison pill)
	]

	# 2. Compile
	result_json_str = service.compile(
		resource_urn='urn:s3:sensitive-bucket',
		obligations=obs,
		target='aws_iam',
		context={'resource_arn': 'arn:aws:s3:::sensitive-bucket'},
	)

	# 3. Verify Output
	policy = json.loads(result_json_str)  # Ensure valid JSON
	statements = policy['Statement']

	# Find the AI blocking statement
	ai_statement = next(s for s in statements if s['Sid'] == 'AmbyteBlockAiTraining')

	assert ai_statement['Effect'] == 'Deny'
	assert 'sagemaker:CreateTrainingJob' in ai_statement['Action']
	# Check simple resource binding
	assert ai_statement['Condition']['StringLike']['sagemaker:InputDataConfig'] == 'arn:aws:s3:::sensitive-bucket'


def test_end_to_end_diff_generation():
	"""
	Scenario:
	1. Create 'Old' Policy (Short retention).
	2. Create 'New' Policy (Longer retention, New Geo Rules).
	3. Use Engine to resolving both internally.
	4. Generate Diff Report.
	"""
	service = PolicyCompilerService()
	diff_engine = SemanticDiffEngine()

	# Old State: 30 Days Retention, No Geo
	obs_old = [make_retention_ob('V1', 30)]
	policy_old = service.rules_engine.resolve('urn:test', obs_old)

	# New State: 365 Days Retention (Permissive change), Geo Added (Restrictive change)
	obs_new = [make_retention_ob('V2', 365), make_geo_ob('GEO-1', allowed=['US'], denied=[])]
	policy_new = service.rules_engine.resolve('urn:test', obs_new)

	# Compute Diff
	report = diff_engine.compute_diff(policy_old, policy_new)
	markdown = report.to_markdown()

	# Verify
	assert report.has_changes

	# Check Retention Change (Permissive because duration increased)
	retention_change = next(c for c in report.changes if c.category == 'Retention')
	assert retention_change.impact == 'PERMISSIVE'
	assert '30' in retention_change.old_value
	assert '365' in retention_change.new_value

	# Check Geo Change (Restrictive because rules added where none existed)
	geo_change = next(c for c in report.changes if c.category == 'Geofencing')
	assert geo_change.change_type == 'ADDED'
	assert geo_change.impact == 'RESTRICTIVE'

	# Check Markdown
	assert 'Policy Diff Report' in markdown
	assert 'Retention' in markdown
	assert 'Geofencing' in markdown

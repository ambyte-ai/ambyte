import json
from datetime import timedelta
from pathlib import Path

import pytest
from ambyte_compiler.diff_engine.service import SemanticDiffEngine
from ambyte_compiler.service import PolicyCompilerService
from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	PrivacyEnhancementRule,
	PrivacyMethod,
	ResourceSelector,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)

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

	snowflake_dir = d / 'snowflake'
	snowflake_dir.mkdir()
	p = snowflake_dir / 'masking.sql'
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
		target=ResourceSelector(include_patterns=['*']),
	)


def make_geo_ob(id: str, allowed: list[str], denied: list[str]) -> Obligation:
	return Obligation(
		id=id,
		title=f'Geo Rule {id}',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		geofencing=GeofencingRule(allowed_regions=allowed, denied_regions=denied),
		target=ResourceSelector(include_patterns=['*']),
	)


def make_ai_ob(id: str, training_allowed: bool) -> Obligation:
	return Obligation(
		id=id,
		title=f'AI Rule {id}',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		ai_model=AiModelConstraint(training_allowed=training_allowed, attribution_text_required='Credit Ambyte'),
		target=ResourceSelector(include_patterns=['*']),
	)


def make_privacy_ob(id: str, method: PrivacyMethod) -> Obligation:
	return Obligation(
		id=id,
		title=f'Privacy Rule {id}',
		description='...',
		provenance=make_provenance(f'SRC-{id}'),
		enforcement_level=EnforcementLevel.BLOCKING,
		privacy=PrivacyEnhancementRule(method=method, parameters={}),
		target=ResourceSelector(include_patterns=['*']),
	)


# ------------------------------------------------------------------------------
# Integration Tests
# ------------------------------------------------------------------------------


def test_pipeline_snowflake_privacy(templates_dir):
	"""
	Scenario:
	1. Two conflicting privacy rules (Unspecified vs Pseudonymization).
	2. Compiler should resolve to Pseudonymization (Stronger wins).
	3. Generator should produce valid Snowflake SQL masking policy using SHA2.
	"""
	service = PolicyCompilerService(templates_path=templates_dir)

	# 1. Input: Conflicting Obligations
	obs = [
		make_privacy_ob('Default', method=PrivacyMethod.UNSPECIFIED),  # Weak
		make_privacy_ob('GDPR-Hash', method=PrivacyMethod.PSEUDONYMIZATION),  # Stronger (Winner)
	]

	# 2. Compile
	result = service.compile(
		resources=[{'urn': 'snowflake:sales_db:customers:email'}],
		obligations=obs,
		target='snowflake',
		context={'input_type': 'STRING', 'allowed_roles': ['ADMIN', 'PII_READER']},
	)

	# 3. Verify Output
	assert isinstance(result, str)
	assert 'CREATE OR REPLACE MASKING POLICY ambyte_mask_email' in result
	# Pseudonymization maps to 'HASH' in generator, which triggers 'sha2(val)' in our test template
	assert 'sha2(val)' in result
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
	result = service.compile(resources=[{'urn': 'api:user_service'}], obligations=obs, target='opa')

	# 3. Verify Output
	assert isinstance(result, dict)
	assert result['resource_urn'] == 'api:user_service'

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
		resources=[{'urn': 's3:sensitive-bucket'}],
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

	# Verify updated Robust Logic (S3 URI Translation & ForAnyValue)
	# It should verify that 'arn:aws:s3:::sensitive-bucket' got translated to 's3://sensitive-bucket/*'
	condition_block = ai_statement['Condition']['ForAnyValue:StringLike']['sagemaker:InputDataConfig']
	assert 's3://sensitive-bucket/*' in condition_block


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

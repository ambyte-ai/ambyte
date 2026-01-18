import json
from datetime import timedelta

from ambyte_compiler.generators.iam_builder import IamPolicyBuilder
from ambyte_rules.models import (
	ConflictTrace,
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import RetentionTrigger

# ==============================================================================
# HELPERS
# ==============================================================================


def make_trace(id_val: str):
	return ConflictTrace(winning_obligation_id=id_val, winning_source_id='TEST', description='...')


# ==============================================================================
# TESTS
# ==============================================================================


def test_iam_geo_restrictions():
	"""
	Verify that Geofencing rules generate both 'Block Explicit Deny'
	and 'Enforce Allowed List' statements.
	"""
	builder = IamPolicyBuilder()

	policy = ResolvedPolicy(
		resource_urn='urn:aws:s3:bucket',
		geofencing=EffectiveGeofencing(
			allowed_regions={'us-east-1', 'eu-central-1'},  # Set is unordered
			blocked_regions={'cn-north-1'},
			reason=make_trace('GEO'),
			is_global_ban=False,
		),
	)

	json_str = builder.build_guardrail_policy(policy, 'arn:aws:s3:::sensitive-bucket')
	doc = json.loads(json_str)

	assert doc['Version'] == '2012-10-17'
	statements = doc['Statement']
	assert len(statements) == 2

	# Check Deny Blocked
	blocked = next(s for s in statements if s['Sid'] == 'AmbyteGeoBlockDeniedRegions')
	assert blocked['Effect'] == 'Deny'
	assert blocked['Resource'] == 'arn:aws:s3:::sensitive-bucket'
	assert blocked['Condition']['StringEquals']['aws:RequestedRegion'] == ['cn-north-1']

	# Check Allow Only
	allowed = next(s for s in statements if s['Sid'] == 'AmbyteGeoEnforceAllowedRegions')
	# Verify sorting happens (Eu before Us)
	assert allowed['Condition']['StringNotEquals']['aws:RequestedRegion'] == ['eu-central-1', 'us-east-1']


def test_iam_global_ban():
	"""
	Verify strict global ban logic (when intersection is empty).
	"""
	builder = IamPolicyBuilder()
	policy = ResolvedPolicy(
		resource_urn='urn:aws:s3:bucket', geofencing=EffectiveGeofencing(is_global_ban=True, reason=make_trace('BAN'))
	)

	json_str = builder.build_guardrail_policy(policy, 'arn:aws:s3:::sensitive-bucket')
	doc = json.loads(json_str)

	stmt = doc['Statement'][0]
	assert stmt['Sid'] == 'AmbyteGeoGlobalBan'
	assert stmt['Effect'] == 'Deny'
	# Matches a custom condition that will always fail or specific logic defined in builder
	assert stmt['Condition']['StringEquals']['ambyte:reason'] == 'global_ban'


def test_iam_ai_restrictions_s3_translation():
	"""
	Verify that AI Training bans block SageMaker actions, and crucially,
	translate the S3 ARN into the S3 URI format SageMaker API expects.
	"""
	builder = IamPolicyBuilder()

	policy = ResolvedPolicy(
		resource_urn='urn:aws:s3:bucket',
		ai_rules=EffectiveAiRules(
			training_allowed=False,  # This should trigger the block
			reason=make_trace('AI'),
			fine_tuning_allowed=True,
			rag_allowed=True,
			attribution_required=False,
			attribution_text='',
		),
	)

	target_arn = 'arn:aws:s3:::training-data'
	json_str = builder.build_guardrail_policy(policy, target_arn)
	doc = json.loads(json_str)

	ai_stmt = doc['Statement'][0]
	assert ai_stmt['Sid'] == 'AmbyteBlockAiTraining'
	assert ai_stmt['Effect'] == 'Deny'

	# Verify expanded action list
	actions = ai_stmt['Action']
	assert 'sagemaker:CreateTrainingJob' in actions
	assert 'sagemaker:CreateProcessingJob' in actions
	assert 'bedrock:InvokeModel' in actions

	# Verify the condition uses ForAnyValue:StringLike and translates ARN -> s3://...
	condition = ai_stmt['Condition']['ForAnyValue:StringLike']['sagemaker:InputDataConfig']

	# Should contain both wildcard and exact match
	assert 's3://training-data/*' in condition
	assert 's3://training-data' in condition
	# Should NOT contain the raw ARN
	assert target_arn not in condition


def test_iam_ai_restrictions_non_s3_fallback():
	"""
	Verify that if the resource is NOT an S3 bucket (e.g. Feature Store),
	it falls back to using the ARN directly.
	"""
	builder = IamPolicyBuilder()
	policy = ResolvedPolicy(
		resource_urn='urn:aws:featurestore', ai_rules=EffectiveAiRules(training_allowed=False, reason=make_trace('AI'))
	)

	target_arn = 'arn:aws:sagemaker:us-east-1:123456789012:feature-group/my-features'
	json_str = builder.build_guardrail_policy(policy, target_arn)
	doc = json.loads(json_str)

	ai_stmt = doc['Statement'][0]
	condition = ai_stmt['Condition']['ForAnyValue:StringLike']['sagemaker:InputDataConfig']

	# Should fall back to list containing the raw ARN
	assert condition == [target_arn]


def test_iam_retention_hold():
	"""
	Verify legal hold logic protects S3 Object Tags.
	"""
	builder = IamPolicyBuilder()
	policy = ResolvedPolicy(
		resource_urn='urn:aws:s3:bucket',
		retention=EffectiveRetention(
			duration=timedelta(days=1),
			is_indefinite=True,  # Triggers lock
			trigger=RetentionTrigger.CREATION_DATE,
			reason=make_trace('HOLD'),
		),
	)

	json_str = builder.build_guardrail_policy(policy, 'arn:aws:s3:::evidence')
	doc = json.loads(json_str)

	stmt = doc['Statement'][0]
	assert stmt['Sid'] == 'AmbyteLockLegalHoldTags'
	assert 's3:DeleteObjectTagging' in stmt['Action']


def test_iam_empty_policy():
	"""Ensure builder handles policies with no relevant constraints gracefully."""
	builder = IamPolicyBuilder()
	policy = ResolvedPolicy(resource_urn='urn:empty')  # No constraints set

	json_str = builder.build_guardrail_policy(policy, 'arn:aws:s3:::empty')
	doc = json.loads(json_str)

	assert doc['Statement'] == []
	assert doc['Version'] == '2012-10-17'

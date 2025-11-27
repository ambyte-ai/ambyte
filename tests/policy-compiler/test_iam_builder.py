import json

from ambyte_rules.models import (
	ConflictTrace,
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectiveRetention,
	ResolvedPolicy,
)
from policy_compiler.generators.iam_builder import IamPolicyBuilder

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


def test_iam_ai_restrictions():
	"""
	Verify that AI Training bans block SageMaker actions on the specific resource.
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
	assert 'sagemaker:CreateTrainingJob' in ai_stmt['Action']
	assert 'bedrock:InvokeModel' in ai_stmt['Action']

	# Verify the condition targets the input config
	assert ai_stmt['Condition']['StringLike']['sagemaker:InputDataConfig'] == target_arn


def test_iam_retention_hold():
	"""
	Verify legal hold logic protects S3 Object Tags.
	"""
	builder = IamPolicyBuilder()
	from datetime import timedelta

	policy = ResolvedPolicy(
		resource_urn='urn:aws:s3:bucket',
		retention=EffectiveRetention(
			duration=timedelta(days=1),
			is_indefinite=True,  # Triggers lock
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

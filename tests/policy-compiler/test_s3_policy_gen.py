import json
from datetime import timedelta

import pytest
from ambyte_compiler.generators.s3_policy import S3BucketPolicyGenerator
from ambyte_rules.models import (
	ConflictTrace,
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePrivacy,
	EffectiveRetention,
	ResolvedPolicy,
)
from ambyte_schemas.models.obligation import PrivacyMethod

# ==============================================================================
# HELPERS & FIXTURES
# ==============================================================================


@pytest.fixture
def generator():
	return S3BucketPolicyGenerator()


def make_trace(id_val='test'):
	return ConflictTrace(
		winning_obligation_id=id_val, winning_source_id='TEST_SOURCE', description='Unit test rationale'
	)


def make_policy(**kwargs):
	"""Creates a ResolvedPolicy with defaults, allowing overrides."""
	base = {
		'resource_urn': 'urn:ambyte:test',
		'contributing_obligation_ids': [],
		'retention': None,
		'geofencing': None,
		'ai_rules': None,
		'purpose': None,
		'privacy': None,
	}
	base.update(kwargs)
	return ResolvedPolicy(**base)


# ==============================================================================
# TESTS
# ==============================================================================


def test_invalid_arn_format(generator):
	"""
	Ensure it raises ValueError if the ARN is not an S3 ARN.
	"""
	policy = make_policy()

	with pytest.raises(ValueError) as exc:
		generator.generate(policy, 'arn:aws:iam::123:role/MyRole')

	assert 'Invalid S3 ARN' in str(exc.value)


def test_arn_normalization(generator):
	"""
	Ensure it correctly generates Bucket AND Object resources regardless of input slash.
	Input: arn:aws:s3:::my-bucket
	Output Resources: ["arn:aws:s3:::my-bucket", "arn:aws:s3:::my-bucket/*"]
	"""
	policy = make_policy(privacy=EffectivePrivacy(method=PrivacyMethod.PSEUDONYMIZATION, reason=make_trace()))

	# Case 1: Clean ARN
	json_1 = generator.generate(policy, 'arn:aws:s3:::clean-bucket')
	doc_1 = json.loads(json_1)
	res_1 = doc_1['Statement'][0]['Resource']
	assert 'arn:aws:s3:::clean-bucket' in res_1
	assert 'arn:aws:s3:::clean-bucket/*' in res_1

	# Case 2: Trailing Slash
	json_2 = generator.generate(policy, 'arn:aws:s3:::slash-bucket/')
	doc_2 = json.loads(json_2)
	res_2 = doc_2['Statement'][0]['Resource']
	assert 'arn:aws:s3:::slash-bucket' in res_2
	assert 'arn:aws:s3:::slash-bucket/*' in res_2


def test_ai_training_block(generator):
	"""
	Scenario: AI Training is forbidden.
	Expectation: Explicit Deny for AWS AI Services (ViaAWSService) and Principals.
	"""
	ai_rules = EffectiveAiRules(training_allowed=False, reason=make_trace())
	policy = make_policy(ai_rules=ai_rules)

	output = generator.generate(policy, 'arn:aws:s3:::ai-data')
	doc = json.loads(output)

	statements = doc['Statement']
	assert len(statements) == 2  # Service Access + Principals

	# Check 1: ViaAWSService Block
	stmt_via = next(s for s in statements if s['Sid'] == 'AmbyteDenyAiServiceAccess')
	assert stmt_via['Effect'] == 'Deny'
	assert 'sagemaker.amazonaws.com' in stmt_via['Condition']['StringEquals']['aws:ViaAWSService']

	# Check 2: Service Principal Block
	stmt_princ = next(s for s in statements if s['Sid'] == 'AmbyteDenyAiServicePrincipals')
	assert stmt_princ['Effect'] == 'Deny'
	assert 'sagemaker.amazonaws.com' in stmt_princ['Principal']['Service']


def test_ai_training_allowed(generator):
	"""
	Scenario: AI Training is allowed.
	Expectation: No blocking statements generated.
	"""
	ai_rules = EffectiveAiRules(training_allowed=True, reason=make_trace())
	policy = make_policy(ai_rules=ai_rules)

	output = generator.generate(policy, 'arn:aws:s3:::safe-data')
	doc = json.loads(output)

	assert len(doc['Statement']) == 0


def test_privacy_tls_enforcement(generator):
	"""
	Scenario: Privacy rule exists (e.g. Masking).
	Expectation: Enforce TLS (Deny if SecureTransport is false).
	"""
	privacy = EffectivePrivacy(method=PrivacyMethod.PSEUDONYMIZATION, reason=make_trace())
	policy = make_policy(privacy=privacy)

	output = generator.generate(policy, 'arn:aws:s3:::pii-data')
	doc = json.loads(output)

	stmt = doc['Statement'][0]
	assert stmt['Sid'] == 'AmbyteEnforceTls'
	assert stmt['Effect'] == 'Deny'
	assert stmt['Condition']['Bool']['aws:SecureTransport'] == 'false'


def test_retention_legal_hold(generator):
	"""
	Scenario: Indefinite retention (Legal Hold).
	Expectation: Deny DeleteObject if object has 'LegalHold' tag.
	"""
	retention = EffectiveRetention(
		duration=timedelta(days=1),
		is_indefinite=True,  # This triggers the logic
		reason=make_trace(),
	)
	policy = make_policy(retention=retention)

	output = generator.generate(policy, 'arn:aws:s3:::evidence')
	doc = json.loads(output)

	stmt = doc['Statement'][0]
	assert stmt['Sid'] == 'AmbyteDenyDeleteOnLegalHold'
	assert stmt['Effect'] == 'Deny'
	assert 's3:DeleteObject' in stmt['Action']
	assert stmt['Condition']['StringEquals']['s3:ExistingObjectTag/LegalHold'] == 'true'


def test_geofencing_global_ban(generator):
	"""
	Scenario: Global Ban active.
	Expectation: Deny ALL actions for everyone except PlatformAdmin.
	"""
	geo = EffectiveGeofencing(is_global_ban=True, reason=make_trace())
	policy = make_policy(geofencing=geo)

	output = generator.generate(policy, 'arn:aws:s3:::banned')
	doc = json.loads(output)

	stmt = doc['Statement'][0]
	assert stmt['Sid'] == 'AmbyteGlobalBanLockdown'
	assert stmt['Action'] == 's3:*'
	# Check the Break-Glass role logic
	assert stmt['Condition']['StringNotEquals']['aws:PrincipalTag/AmbyteRole'] == 'PlatformAdmin'


def test_combined_policy(generator):
	"""
	Scenario: Multiple constraints active simultaneously.
	Expectation: All corresponding statements are generated.
	"""
	policy = make_policy(
		ai_rules=EffectiveAiRules(training_allowed=False, reason=make_trace()),  # +2 Statements
		privacy=EffectivePrivacy(method=PrivacyMethod.ANONYMIZATION, reason=make_trace()),  # +1 Statement
	)

	output = generator.generate(policy, 'arn:aws:s3:::combo')
	doc = json.loads(output)

	statements = doc['Statement']
	assert len(statements) == 3

	sids = [s['Sid'] for s in statements]
	assert 'AmbyteDenyAiServiceAccess' in sids
	assert 'AmbyteDenyAiServicePrincipals' in sids
	assert 'AmbyteEnforceTls' in sids

import json
import logging
from typing import Any

from ambyte_rules.models import ResolvedPolicy

from apps.policy_compiler.ambyte_compiler.validators import IamJsonValidator

logger = logging.getLogger(__name__)


class IamPolicyBuilder:
	"""
	Generates AWS IAM Policy Documents (JSON) based on ResolvedPolicies.

	Strategy: "Negative Logic" (Guardrails).
	We generate explicit DENY statements for violations. This ensures that
	even if a user has AdministratorAccess, these specific compliance
	constraints (like Geofencing) will block them.
	"""

	def __init__(self):
		# Initialize the validator once
		self._validator = IamJsonValidator()

	def build_guardrail_policy(self, policy: ResolvedPolicy, resource_arn: str) -> str:
		"""
		Generates a Resource-Based Policy or Permission Boundary JSON.

		Args:
		    policy: The resolved Ambyte rules.
		    resource_arn: The AWS ARN of the target resource (e.g. arn:aws:s3:::my-bucket).

		Returns:
		    A JSON string representing the IAM Policy.

		Raises:
		    ValueError: If the generated policy fails structural validation.
		"""  # noqa: E101
		statements: list[dict[str, Any]] = []

		# 1. Geofencing (Region Restrictions)
		if policy.geofencing:
			# A. Global Ban
			if policy.geofencing.is_global_ban:
				statements.append(
					{
						'Sid': 'AmbyteGeoGlobalBan',
						'Effect': 'Deny',
						'Action': '*',
						'Resource': resource_arn,
						'Condition': {'StringEquals': {'ambyte:reason': 'global_ban'}},
					}
				)
			else:
				# B. Explicit Deny List
				if policy.geofencing.blocked_regions:
					statements.append(
						{
							'Sid': 'AmbyteGeoBlockDeniedRegions',
							'Effect': 'Deny',
							'Action': '*',
							'Resource': resource_arn,
							'Condition': {
								'StringEquals': {'aws:RequestedRegion': sorted(policy.geofencing.blocked_regions)}
							},
						}
					)

				# C. Allowed List (Deny if NOT in allowed)
				if policy.geofencing.allowed_regions:
					statements.append(
						{
							'Sid': 'AmbyteGeoEnforceAllowedRegions',
							'Effect': 'Deny',
							'Action': '*',
							'Resource': resource_arn,
							'Condition': {
								'StringNotEquals': {'aws:RequestedRegion': sorted(policy.geofencing.allowed_regions)}
							},
						}
					)

		# 2. AI & ML Restrictions
		# If training is forbidden, we block SageMaker and Bedrock access to this resource.
		if policy.ai_rules and not policy.ai_rules.training_allowed:
			# Calculate S3 patterns for SageMaker's API matching
			# SageMaker InputDataConfig matches against 's3://bucket/key', not ARNs.
			s3_patterns = self._get_sagemaker_input_patterns(resource_arn)

			statements.append(
				{
					'Sid': 'AmbyteBlockAiTraining',
					'Effect': 'Deny',
					'Action': [
						# Training & Tuning
						'sagemaker:CreateTrainingJob',
						'sagemaker:CreateHyperParameterTuningJob',
						'sagemaker:CreateAutoMLJob',
						# Processing (DataBrew, Spark)
						'sagemaker:CreateProcessingJob',
						# Transformations (Batch Inference)
						'sagemaker:CreateTransformJob',
						# Labeling (Exposes data to humans/GroundTruth)
						'sagemaker:CreateLabelingJob',
						# Bedrock Customization
						'bedrock:CreateModelCustomizationJob',
						# Direct Model Invocation (RAG Context)
						'bedrock:InvokeModel',
					],
					# We block the actions on * (Any Resource) but conditional on the Input Data
					'Resource': '*',
					'Condition': {
						# ForAnyValue is required because InputDataConfig is an array in the API.
						# StringLike allows us to match s3://bucket/* patterns.
						'ForAnyValue:StringLike': {'sagemaker:InputDataConfig': s3_patterns}
					},
				}
			)

		# 3. Retention (Tagging Enforcer)
		# We can't easily force deletion via IAM, but we can deny modification
		# of the Legal Hold tags if retention is indefinite.
		if policy.retention and policy.retention.is_indefinite:
			statements.append(
				{
					'Sid': 'AmbyteLockLegalHoldTags',
					'Effect': 'Deny',
					'Action': ['s3:DeleteObjectTagging', 's3:PutObjectTagging'],
					'Resource': resource_arn,
					'Condition': {'StringEquals': {'s3:ExistingObjectTag/LegalHold': 'true'}},
				}
			)

		# 4. Purpose Restrictions (ABAC)
		# We rely on Principal Tags (aws:PrincipalTag/ambyte:purpose) to map intent.
		if policy.purpose:
			# A. Block Explicitly Denied Purposes
			if policy.purpose.denied_purposes:
				statements.append(
					{
						'Sid': 'AmbyteBlockDeniedPurposes',
						'Effect': 'Deny',
						'Action': '*',
						'Resource': resource_arn,
						'Condition': {
							'StringEquals': {'aws:PrincipalTag/ambyte:purpose': sorted(policy.purpose.denied_purposes)}
						},
					}
				)

			# B. Enforce Allowed Purposes (Whitelist)
			# If the user does not have the correct tag, or has a wrong tag, they are blocked.
			if policy.purpose.allowed_purposes:
				statements.append(
					{
						'Sid': 'AmbyteEnforceAllowedPurposes',
						'Effect': 'Deny',
						'Action': '*',
						'Resource': resource_arn,
						'Condition': {
							'StringNotEquals': {
								'aws:PrincipalTag/ambyte:purpose': sorted(policy.purpose.allowed_purposes)
							}
						},
					}
				)

		# 5. Privacy Requirements (Encryption Enforcement)
		# If active privacy rules exist (e.g. Masking), we enforce TLS so raw data
		# cannot be sniffed before it reaches the compute layer that performs the masking.
		if policy.privacy:
			statements.append(
				{
					'Sid': 'AmbyteEnforcePrivacyEncryption',
					'Effect': 'Deny',
					'Action': '*',
					'Resource': resource_arn,
					'Condition': {'Bool': {'aws:SecureTransport': 'false'}},
				}
			)

		policy_doc = {'Version': '2012-10-17', 'Statement': statements}

		json_output = json.dumps(policy_doc, indent=4)

		# --- Self-Validation Step ---
		# Ensure the builder never produces broken IAM Policies
		validation_result = self._validator.validate(policy_doc)
		if not validation_result.is_valid:
			error_msg = '; '.join(validation_result.errors)
			logger.error(f'Generated IAM Policy for {resource_arn} is invalid: {error_msg}')
			raise ValueError(f'IAM Generation Failed: {error_msg}')

		return json_output

	def _get_sagemaker_input_patterns(self, resource_arn: str) -> list[str]:
		"""
		Helper to translate an AWS ARN into the S3 URI format SageMaker uses
		for InputDataConfig matching.

		Input: arn:aws:s3:::my-sensitive-bucket
		Output: ['s3://my-sensitive-bucket/*', 's3://my-sensitive-bucket']
		"""
		# If it's not an S3 ARN, fallback to using the ARN itself (e.g. Feature Store ARN)
		if not resource_arn.startswith('arn:aws:s3:::'):
			return [resource_arn]

		# Strip the ARN prefix
		clean_path = resource_arn.replace('arn:aws:s3:::', '')

		# For SageMaker matching, we generally want to block the whole bucket prefix
		# if the policy applies to that resource.
		return [f's3://{clean_path}/*', f's3://{clean_path}']

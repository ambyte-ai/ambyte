import json
from typing import Any

from ambyte_rules.models import ResolvedPolicy


class IamPolicyBuilder:
	"""
	Generates AWS IAM Policy Documents (JSON) based on ResolvedPolicies.

	Strategy: "Negative Logic" (Guardrails).
	We generate explicit DENY statements for violations. This ensures that
	even if a user has AdministratorAccess, these specific compliance
	constraints (like Geofencing) will block them.
	"""

	def build_guardrail_policy(self, policy: ResolvedPolicy, resource_arn: str) -> str:
		"""
		Generates a Resource-Based Policy or Permission Boundary JSON.

		Args:
		policy: The resolved Ambyte rules.
		resource_arn: The AWS ARN of the target resource (e.g. arn:aws:s3:::my-bucket).

		Returns:
		A JSON string representing the IAM Policy.
		"""
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
			statements.append(
				{
					'Sid': 'AmbyteBlockAiTraining',
					'Effect': 'Deny',
					'Action': [
						'sagemaker:CreateTrainingJob',
						'sagemaker:CreateHyperParameterTuningJob',
						'sagemaker:CreateAutoMLJob',
						'bedrock:CreateModelCustomizationJob',
						'bedrock:InvokeModel',  # Prevent using data in RAG/Inference if strictly mapped
					],
					'Resource': '*',  # SageMaker jobs often don't resource-level lock inputs easily,
					'Condition': {  # so we block the action contextually if possible, or bind to resource
						# This is an approximation. In real AWS, restricting input sources # TODO
						# for SageMaker requires complex VPC Endpoint policies or S3 Bucket Policies.
						# Here we generate a Bucket Policy snippet assuming 'resource_arn' is an S3 bucket.
						'StringLike': {'sagemaker:InputDataConfig': resource_arn}
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

		policy_doc = {'Version': '2012-10-17', 'Statement': statements}

		return json.dumps(policy_doc, indent=4)

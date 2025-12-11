import json
from typing import Any

from ambyte_rules.models import ResolvedPolicy


class S3BucketPolicyGenerator:
	"""
	Generates AWS S3 Bucket Policies (Resource-Based Policies).

	This acts as the "Data Perimeter" defense. While Identity policies (IAM)
	restrict the User, this policy restricts the Service itself.

	For example, it can explicitly forbid the SageMaker Service Principal
	from reading data, regardless of the permissions of the user running the job.
	"""

	def generate(self, policy: ResolvedPolicy, resource_arn: str) -> str:
		"""
		Builds the JSON Bucket Policy.

		Args:
		    policy: The resolved Ambyte rules.
		    resource_arn: The ARN of the bucket (e.g. arn:aws:s3:::my-bucket).

		Returns:
		    A JSON string representing the S3 Bucket Policy.
		"""  # noqa: E101
		# Validate ARN format
		if not resource_arn.startswith('arn:aws:s3:::'):
			raise ValueError(f"Invalid S3 ARN: '{resource_arn}'. Must start with 'arn:aws:s3:::'.")

		# Handle cases where input might already have /* or /
		# rstrip is character-based, so it handles "/*" and "/" variations
		base_arn = resource_arn.rstrip('/*').rstrip('/')

		# Define normalized resources
		bucket_arn = base_arn
		object_arn = f'{base_arn}/*'

		statements: list[dict[str, Any]] = []

		# 1. AI Service Perimeter (The "SageMaker Block")
		# If training is forbidden, we deny access to any request originating
		# from AWS AI services, even if the IAM Role has permission.
		if policy.ai_rules and not policy.ai_rules.training_allowed:
			statements.append(
				{
					'Sid': 'AmbyteDenyAiServiceAccess',
					'Effect': 'Deny',
					'Principal': '*',  # Apply to everyone, including Account Root
					'Action': ['s3:GetObject', 's3:ListBucket'],
					'Resource': [bucket_arn, object_arn],
					'Condition': {
						# Block requests where the "Via" service is SageMaker or Bedrock.
						# This catches cases where the service accesses data on behalf of a user.
						'StringEquals': {'aws:ViaAWSService': ['sagemaker.amazonaws.com', 'bedrock.amazonaws.com']}
					},
				}
			)

			# We also block the Service Principals directly for good measure,
			# covering cases like Data Wrangler or internal service calls.
			statements.append(
				{
					'Sid': 'AmbyteDenyAiServicePrincipals',
					'Effect': 'Deny',
					'Principal': {'Service': ['sagemaker.amazonaws.com', 'bedrock.amazonaws.com']},
					'Action': ['s3:GetObject', 's3:ListBucket'],
					'Resource': [bucket_arn, object_arn],
				}
			)

		# 2. Privacy & Security (Encryption in Transit)
		# If privacy rules exist, we mandate TLS to ensure data isn't sniffed
		# before it hits the compute layer (where masking would happen).
		if policy.privacy:
			statements.append(
				{
					'Sid': 'AmbyteEnforceTls',
					'Effect': 'Deny',
					'Principal': '*',
					'Action': 's3:*',
					'Resource': [bucket_arn, object_arn],
					'Condition': {'Bool': {'aws:SecureTransport': 'false'}},
				}
			)

		# 3. Retention (Immutable Deletes)
		# If data is under Legal Hold (Indefinite Retention), we deny deletion.
		# This is stronger than IAM because it blocks the root account in many configs
		# (unless they remove the policy first).
		if policy.retention and policy.retention.is_indefinite:
			statements.append(
				{
					'Sid': 'AmbyteDenyDeleteOnLegalHold',
					'Effect': 'Deny',
					'Principal': '*',
					'Action': ['s3:DeleteObject', 's3:DeleteObjectVersion'],
					'Resource': object_arn,
					# We rely on the object tags. If the object has the tag, you can't delete it.
					# Note: This requires the object to actually have the tag.
					'Condition': {'StringEquals': {'s3:ExistingObjectTag/LegalHold': 'true'}},
				}
			)

		# 4. Geofencing (Network Perimeter)
		# Note: This requires knowing the Allowed VPC IDs. Since ResolvedPolicy
		# usually deals with "Regions" (countries), standard VPC logic is hard to
		# generate generically without more context.
		# However, if we have a "Global Ban", we can lock it down completely.
		if policy.geofencing and policy.geofencing.is_global_ban:
			statements.append(
				{
					'Sid': 'AmbyteGlobalBanLockdown',
					'Effect': 'Deny',
					'Principal': '*',
					'Action': 's3:*',
					'Resource': [bucket_arn, object_arn],
					'Condition': {
						# (This assumes a specific role ARN or UserID convention)
						# For now, we simply block everything not tagged "BreakGlass"
						'StringNotEquals': {'aws:PrincipalTag/AmbyteRole': 'PlatformAdmin'}
					},
				}
			)

		policy_doc = {'Version': '2012-10-17', 'Statement': statements}

		return json.dumps(policy_doc, indent=4)

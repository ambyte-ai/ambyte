from pathlib import Path
from typing import Any, Literal

from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.obligation import Obligation, PrivacyMethod

from apps.policy_compiler.ambyte_compiler.generators import (
	IamPolicyBuilder,
	LocalPythonGenerator,
	RegoDataBuilder,
	S3BucketPolicyGenerator,
	SnowflakeGenerator,
)
from apps.policy_compiler.ambyte_compiler.matcher import ResourceMatcher

TargetPlatform = Literal['snowflake', 'opa', 'aws_iam', 'local']


class PolicyCompilerService:
	"""
	The main entry point for the Policy-as-Code subsystem.

	This service orchestrates the flow from:
	Raw Obligations + Inventory -> Matching -> Conflict Resolution -> Optimized Code Generation.
	"""

	def __init__(self, templates_path: Path | None = None):
		# 1. The Brain (Logic)
		self.rules_engine = ConflictResolutionEngine()
		self.matcher = ResourceMatcher()

		# 2. The Hands (Generators)
		# We initialize generators lazily or eagerly. Eager is fine for now.
		if templates_path:
			self.snowflake_gen = SnowflakeGenerator(template_dir=templates_path)
		else:
			self.snowflake_gen = None  # type: ignore

		self.rego_gen = RegoDataBuilder()
		self.iam_gen = IamPolicyBuilder()
		self.s3_gen = S3BucketPolicyGenerator()

		self.local_gen = LocalPythonGenerator()

	def compile(
		self,
		resources: list[dict[str, Any]],
		obligations: list[Obligation],
		target: TargetPlatform,
		context: dict[str, str | list[str]] | None = None,
	) -> str | dict:
		"""
		Compiles obligations into an executable artifact for a specific target.

		Args:
		    resources: List of dictionaries representing the inventory.
		               Format: [{'urn': '...', 'tags': {'env': 'prod', ...}}]
		    obligations: List of all defined legal/contractual rules.
		    target: The system we are generating code for.
		    context: Extra parameters (e.g. 'project_name', 'git_hash', 'input_type').

		Returns:
		    str: SQL/JSON string (Snowflake, IAM, Local).
		    dict: JSON object (OPA data bundle).
		"""  # noqa: E101
		if context is None:
			context = {}

		# --- Target: LOCAL (Bulk Python Artifact) ---
		# Generates a bundle containing resolved policies for ALL provided resources.
		if target == 'local':
			return self._compile_local(resources, obligations, context)

		# --- Single Resource Targets ---
		# For cloud targets (Snowflake/OPA/IAM), we currently enforce single-resource processing
		# per call to keep the artifact output granular (one file per resource).
		if len(resources) != 1:
			raise ValueError(
				f"Target '{target}' expects exactly one resource context. "
				f'Received {len(resources)}. For bulk processing, use target="local" '
				'or iterate in the caller.'
			)

		target_res = resources[0]
		urn = str(target_res['urn'])
		tags = target_res.get('tags', {})

		# Step 1: Matching (Filter Global Obligations -> Local Scope)
		applicable_obligations = [ob for ob in obligations if self.matcher.matches(urn, tags, ob)]

		# Step 2: Resolve Conflicts
		# This reduces N conflicting rules into 1 mathematical truth for this specific URN.
		effective_policy: ResolvedPolicy = self.rules_engine.resolve(urn, applicable_obligations)

		# Step 3: Route to Generator
		if target == 'snowflake':
			return self._compile_snowflake(effective_policy, context)
		if target == 'opa':
			return self._compile_opa(effective_policy)
		if target == 'aws_iam':
			return self._compile_iam(effective_policy, context)

		raise ValueError(f'Unsupported compilation target: {target}')

	def _compile_local(self, resources: list[dict[str, Any]], obligations: list[Obligation], context: dict) -> str:
		"""
		Generates the 'local_policies.json' Bundle used by ambyte-sdk in LOCAL mode.
		Resolves policies for every item in the inventory.
		"""
		resolved_policies = []

		for res in resources:
			urn = str(res['urn'])
			tags = res.get('tags', {})

			# 1. Matching
			# We test every obligation against this resource's specific context (URN + Tags)
			applicable = [ob for ob in obligations if self.matcher.matches(urn, tags, ob)]

			# 2. Resolution
			# Even if 'applicable' is empty, we resolve it to generate a default (Open) policy object
			# which prevents "Policy Not Found" errors at runtime.
			policy = self.rules_engine.resolve(urn, applicable)
			resolved_policies.append(policy)

		# 3. Extract Metadata from context
		project_name = str(context.get('project_name', 'unknown'))
		git_hash = str(context.get('git_hash', '')) or None

		# 4. Generate Artifact
		return self.local_gen.generate(policies=resolved_policies, project_name=project_name, git_hash=git_hash)

	def _compile_snowflake(self, policy: ResolvedPolicy, context: dict) -> str:
		"""Generates Snowflake SQL."""
		if not self.snowflake_gen:
			raise RuntimeError('SnowflakeGenerator not initialized. Provide templates_path.')

		# Extract context
		input_type = str(context.get('input_type', 'VARCHAR'))
		ref_column = str(context.get('ref_column', 'ID'))  # Used for Row Access Policy binding

		allowed_roles = context.get('allowed_roles', [])
		if isinstance(allowed_roles, str):
			allowed_roles = [allowed_roles]

		sql_statements = []
		obs_count = len(policy.contributing_obligation_ids)

		if policy.privacy:
			# Safety check: Method might be stored as an int in the ResolvedPolicy
			pm_val = policy.privacy.method
			pm_name = pm_val.name if hasattr(pm_val, 'name') else PrivacyMethod(pm_val).name
			masking_sql = self.snowflake_gen.generate_masking_policy(
				policy_name=f'ambyte_mask_{policy.resource_urn.split(":")[-1]}',
				input_type=input_type,
				method=policy.privacy.method,
				allowed_roles=allowed_roles,  # type: ignore
				comment=(
					f'Source: {policy.privacy.reason.winning_source_id}. Method: {pm_name}. Obligations: {obs_count}'
				),
			)
			sql_statements.append(masking_sql)

		if policy.purpose:
			denied_list = sorted(policy.purpose.denied_purposes)
			rap_sql = self.snowflake_gen.generate_row_access_policy(
				policy_name=f'ambyte_row_access_{policy.resource_urn.split(":")[-1]}',
				input_type=input_type,
				ref_column=ref_column,
				allowed_roles=allowed_roles,  # type: ignore
				denied_roles=[],
				denied_purposes=denied_list,
				comment=(
					f'Source: {policy.purpose.reason.winning_source_id}. '
					f'Denied Purposes: {len(denied_list)}. '
					f'Obligations: {obs_count}'
				),
			)
			sql_statements.append(rap_sql)

		if not sql_statements:
			return f'-- No active Privacy or Purpose constraints found for {policy.resource_urn}'

		return '\n\n'.join(sql_statements)

	def _compile_opa(self, policy: ResolvedPolicy) -> dict:
		return self.rego_gen.build_bundle_data(policy)

	def _compile_iam(self, policy: ResolvedPolicy, context: dict) -> str:
		"""
		Generates AWS IAM JSON.
		Switches between Identity Policies (for Users/Roles) and Resource Policies (Buckets)
		based on the 'iam_policy_type' context flag and resource type.
		"""
		resource_arn = str(context.get('resource_arn', policy.resource_urn))

		# Default to 'identity' for backwards compatibility
		# Options: 'identity' (Permission Boundary) | 'resource' (Bucket Policy)
		policy_type = str(context.get('iam_policy_type', 'identity')).lower()

		if policy_type == 'resource':
			# Check if we have a generator for this resource type
			if resource_arn.startswith('arn:aws:s3:::'):
				return self.s3_gen.generate(policy, resource_arn)
			# We currently only support Resource Policies for S3
			raise ValueError(
				f"Resource policy generation requested, but ARN '{resource_arn}' "
				'is not a supported resource type (S3 only).'
			)

		# Default: Generate Identity / Guardrail Policy
		return self.iam_gen.build_guardrail_policy(policy, resource_arn)

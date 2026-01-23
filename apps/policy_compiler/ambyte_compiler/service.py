from pathlib import Path
from typing import Any, Literal

from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.obligation import Obligation, PrivacyMethod

from ambyte_compiler.generators import (
	DatabricksGenerator,
	IamPolicyBuilder,
	LocalPythonGenerator,
	RegoDataBuilder,
	S3BucketPolicyGenerator,
	SnowflakeGenerator,
)
from ambyte_compiler.matcher import ResourceMatcher

TargetPlatform = Literal['snowflake', 'opa', 'aws_iam', 'local', 'databricks']


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
			self.snowflake_gen = SnowflakeGenerator(template_dir=templates_path / 'snowflake')
			self.databricks_gen = DatabricksGenerator(template_dir=templates_path / 'databricks')
		else:
			self.snowflake_gen = None  # type: ignore
			self.databricks_gen = None  # type: ignore

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
		if target == 'databricks':
			return self._compile_databricks(effective_policy, context)

		raise ValueError(f'Unsupported compilation target: {target}')

	def compile_from_policy(
		self,
		policy: ResolvedPolicy,
		target: TargetPlatform,
		context: dict[str, str | list[str]] | None = None,
	) -> str | dict:
		"""
		Compiles a pre-resolved ResolvedPolicy object into an executable artifact.

		This bypasses matching and resolution, making it ideal for Connectors
		that read a pre-compiled 'local_policies.json' bundle.
		"""
		if context is None:
			context = {}

		if target == 'snowflake':
			return self._compile_snowflake(policy, context)
		if target == 'opa':
			return self._compile_opa(policy)
		if target == 'aws_iam':
			return self._compile_iam(policy, context)
		if target == 'databricks':
			return self._compile_databricks(policy, context)

		if target == 'local':
			return policy.model_dump_json(exclude_none=True)

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

	def _compile_databricks(self, policy: ResolvedPolicy, context: dict) -> str:
		"""Generates Databricks Unity Catalog SQL."""
		if not self.databricks_gen:
			raise RuntimeError('DatabricksGenerator not initialized. Provide templates_path.')

		# Extract context
		input_type = str(context.get('input_type', 'STRING'))
		ref_column = str(context.get('ref_column', 'id'))

		# This is typically populated from databricks_mappings.yaml by the caller.
		group_mapping = context.get('group_mapping', {})

		# Prepare Group Sets
		allowed_groups_set = set()
		denied_groups_set = set()

		# 1. Populate from Context overrides (Legacy support / Explicit overrides)
		ctx_allowed = context.get('allowed_groups', [])
		if isinstance(ctx_allowed, str):
			allowed_groups_set.add(ctx_allowed)
		else:
			allowed_groups_set.update(ctx_allowed)

		# 2. Resolve Groups from Policy Purposes
		if policy.purpose:
			# A. Allowed Purposes -> Allowed Groups
			for purpose in policy.purpose.allowed_purposes:
				key = purpose.upper()
				groups = group_mapping.get(key, [])
				allowed_groups_set.update(groups)

			# B. Denied Purposes -> Denied Groups
			for purpose in policy.purpose.denied_purposes:
				key = purpose.upper()
				groups = group_mapping.get(key, [])
				denied_groups_set.update(groups)

		# Convert to sorted lists for deterministic SQL generation
		allowed_groups = sorted(allowed_groups_set)
		denied_groups = sorted(denied_groups_set)

		# 3. Retrieve Value Mapping (RLS)
		# Format: {'US': ['us-group'], 'EU': ['eu-group']}
		# This is typically passed in via context from resource-level config
		value_mapping = context.get('value_mapping', {})

		sql_statements = []
		obs_count = len(policy.contributing_obligation_ids)

		# --- GENERATE MASKING POLICY ---
		if policy.privacy:
			pm_val = policy.privacy.method
			pm_name = pm_val.name if hasattr(pm_val, 'name') else PrivacyMethod(pm_val).name
			masking_sql = self.databricks_gen.generate_masking_udf(
				policy_name=f'ambyte_mask_{policy.resource_urn.split(".")[-1]}',
				input_type=input_type,
				method=policy.privacy.method,
				allowed_groups=allowed_groups,
				comment=(
					f'Source: {policy.privacy.reason.winning_source_id}. Method: {pm_name}. Obligations: {obs_count}'
				),
			)
			sql_statements.append(masking_sql)

		# --- GENERATE ROW FILTER ---
		if policy.purpose or policy.geofencing or value_mapping:
			denied_list = sorted(policy.purpose.denied_purposes) if policy.purpose else []

			row_filter_sql = self.databricks_gen.generate_row_filter_udf(
				policy_name=f'ambyte_row_filter_{policy.resource_urn.split(".")[-1]}',
				ref_column=ref_column,
				input_type=input_type,
				allowed_groups=allowed_groups,
				denied_groups=denied_groups,
				value_mapping=value_mapping,
				comment=(
					f'Source: {policy.purpose.reason.winning_source_id if policy.purpose else "Config"}. '
					f'Denied Purposes: {len(denied_list)}. '
					f'Obligations: {obs_count}'
				),
			)
			sql_statements.append(row_filter_sql)

		if not sql_statements:
			return f'-- No active Privacy or Purpose constraints found for {policy.resource_urn}'

		return '\n\n'.join(sql_statements)

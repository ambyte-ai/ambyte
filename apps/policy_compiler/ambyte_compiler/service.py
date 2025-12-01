from pathlib import Path
from typing import Literal

from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.obligation import Obligation

from apps.policy_compiler.ambyte_compiler.generators.iam_builder import IamPolicyBuilder
from apps.policy_compiler.ambyte_compiler.generators.rego_builder import RegoDataBuilder
from apps.policy_compiler.ambyte_compiler.generators.snowflake_sql import SnowflakeGenerator

TargetPlatform = Literal['snowflake', 'opa', 'aws_iam']


class PolicyCompilerService:
	"""
	The main entry point for the Policy-as-Code subsystem.

	This service orchestrates the flow from:
	Raw Obligations -> Conflict Resolution -> Optimized Code Generation.
	"""

	def __init__(self, templates_path: Path | None = None):
		# 1. The Brain (Logic)
		self.rules_engine = ConflictResolutionEngine()

		# 2. The Hands (Generators)
		# We initialize generators lazily or eagerly. Eager is fine for now.
		if templates_path:
			self.snowflake_gen = SnowflakeGenerator(template_dir=templates_path)
		else:
			# Fallback for tests or non-SQL usage
			self.snowflake_gen = None  # type: ignore

		self.rego_gen = RegoDataBuilder()
		self.iam_gen = IamPolicyBuilder()

	def compile(
		self,
		resource_urn: str,
		obligations: list[Obligation],
		target: TargetPlatform,
		# Context args for specific generators
		context: dict[str, str | list[str]] | None = None,
	) -> str | dict:
		"""
		Compiles a list of obligations into an executable artifact for a specific target.

		Args:
		resource_urn: The ID of the data/model being protected.
		obligations: List of all applicable legal/contractual rules.
		target: The system we are generating code for ('snowflake', 'opa', 'aws_iam').
		context: Extra parameters needed for generation (e.g., 'input_type' for SQL).

		Returns:
		str: SQL or JSON string (for Snowflake/IAM).
		dict: JSON object (for OPA data bundle).
		"""
		if context is None:
			context = {}

		# Step 1: Resolve Conflicts
		# This reduces 50 conflicting rules into 1 mathematical truth.
		effective_policy: ResolvedPolicy = self.rules_engine.resolve(resource_urn, obligations)

		# Step 2: Route to Generator
		if target == 'snowflake':
			return self._compile_snowflake(effective_policy, context)
		if target == 'opa':
			return self._compile_opa(effective_policy)
		if target == 'aws_iam':
			return self._compile_iam(effective_policy, context)

		raise ValueError(f'Unsupported compilation target: {target}')

	def _compile_snowflake(self, policy: ResolvedPolicy, context: dict) -> str:
		"""
		Generates Snowflake SQL for both Column-level (Masking) and Row-level (Access) security.
		"""
		if not self.snowflake_gen:
			raise RuntimeError('SnowflakeGenerator not initialized. Provide templates_path.')

		# Extract context
		input_type = str(context.get('input_type', 'VARCHAR'))
		ref_column = str(context.get('ref_column', 'ID'))  # Used for Row Access Policy binding

		allowed_roles = context.get('allowed_roles', [])
		if isinstance(allowed_roles, str):
			allowed_roles = [allowed_roles]

		sql_statements = []

		# 1. Privacy / Masking Policy (Column Level)
		# Resolved via PrivacySolver (e.g. Differential Privacy vs Pseudonymization)
		if policy.privacy:
			masking_sql = self.snowflake_gen.generate_masking_policy(
				policy_name=f'ambyte_mask_{policy.resource_urn.split(":")[-1]}',
				input_type=input_type,
				method=policy.privacy.method,
				allowed_roles=allowed_roles,  # type: ignore
				comment=f'Source: {policy.privacy.reason.winning_source_id}. Method: {policy.privacy.method.name}',
			)
			sql_statements.append(masking_sql)

		# 2. Purpose / Row Access Policy (Row Level)
		# Resolved via PurposeSolver (e.g. Blocking Marketing use)
		if policy.purpose:
			# Convert sets to sorted lists for deterministic SQL generation
			denied_list = sorted(policy.purpose.denied_purposes)

			rap_sql = self.snowflake_gen.generate_row_access_policy(
				policy_name=f'ambyte_row_access_{policy.resource_urn.split(":")[-1]}',
				input_type=input_type,
				ref_column=ref_column,
				allowed_roles=allowed_roles,  # type: ignore
				denied_roles=[],  # Can be mapped from denied purposes if needed
				denied_purposes=denied_list,
				comment=f'Source: {policy.purpose.reason.winning_source_id}. Denied Purposes: {len(denied_list)}',
			)
			sql_statements.append(rap_sql)

		if not sql_statements:
			return f'-- No active Privacy or Purpose constraints found for {policy.resource_urn}'

		return '\n\n'.join(sql_statements)

	def _compile_opa(self, policy: ResolvedPolicy) -> dict:
		# OPA expects a JSON bundle
		return self.rego_gen.build_bundle_data(policy)

	def _compile_iam(self, policy: ResolvedPolicy, context: dict) -> str:
		# IAM needs the native ARN
		resource_arn = str(context.get('resource_arn', policy.resource_urn))
		return self.iam_gen.build_guardrail_policy(policy, resource_arn)

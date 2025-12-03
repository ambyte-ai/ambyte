from pathlib import Path
from typing import Literal

from ambyte_rules.engine import ConflictResolutionEngine
from ambyte_rules.models import ResolvedPolicy
from ambyte_schemas.models.obligation import Obligation

from apps.policy_compiler.ambyte_compiler.generators import (
	IamPolicyBuilder,
	LocalPythonGenerator,
	RegoDataBuilder,
	SnowflakeGenerator,
)

TargetPlatform = Literal['snowflake', 'opa', 'aws_iam', 'local']


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
			self.snowflake_gen = None  # type: ignore

		self.rego_gen = RegoDataBuilder()
		self.iam_gen = IamPolicyBuilder()

		self.local_gen = LocalPythonGenerator()

	def compile(
		self,
		resource_urn: str | list[str],
		obligations: list[Obligation],
		target: TargetPlatform,
		context: dict[str, str | list[str]] | None = None,
	) -> str | dict:
		"""
		Compiles obligations into an executable artifact for a specific target.

		Args:
			resource_urn: The ID(s) of the resource to compile for.
					Pass a List[str] only if target='local' (Bulk Compilation).
			obligations: List of all applicable legal/contractual rules.
			target: The system we are generating code for.
			context: Extra parameters (e.g. 'project_name', 'git_hash', 'input_type').

		Returns:
			str: SQL/JSON string (Snowflake, IAM, Local).
			dict: JSON object (OPA data bundle).
		"""
		if context is None:
			context = {}

		# --- Target: LOCAL (Bulk Python Artifact) ---
		if target == 'local':
			return self._compile_local(resource_urn, obligations, context)

		# --- Single Resource Targets ---
		# For non-local targets, we enforce single URN processing for now. # TODO
		if isinstance(resource_urn, list):
			raise ValueError(f"Target '{target}' does not support bulk compilation. Pass a single URN.")

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

	def _compile_local(self, urns: str | list[str], obligations: list[Obligation], context: dict) -> str:
		"""
		Generates the 'local_policies.json' artifact containing ALL resolved policies.
		"""
		target_urns = [urns] if isinstance(urns, str) else urns
		resolved_policies = []

		# 1. Bulk Resolution
		# In a real system, we would filter 'obligations' per URN based on tags/pattern matching
		# before passing to resolve(). For MVP, we assume global scope or pre-filtered inputs. # TODO
		for urn in target_urns:
			# We treat the passed obligations as the "Candidate Set" for this resource.
			policy = self.rules_engine.resolve(urn, obligations)
			resolved_policies.append(policy)

		# 2. Extract Metadata from context
		project_name = str(context.get('project_name', 'unknown'))
		git_hash = str(context.get('git_hash', '')) or None

		# 3. Generate Artifact
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

		if policy.privacy:
			masking_sql = self.snowflake_gen.generate_masking_policy(
				policy_name=f'ambyte_mask_{policy.resource_urn.split(":")[-1]}',
				input_type=input_type,
				method=policy.privacy.method,
				allowed_roles=allowed_roles,  # type: ignore
				comment=f'Source: {policy.privacy.reason.winning_source_id}. Method: {policy.privacy.method.name}',
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
				comment=f'Source: {policy.purpose.reason.winning_source_id}. Denied Purposes: {len(denied_list)}',
			)
			sql_statements.append(rap_sql)

		if not sql_statements:
			return f'-- No active Privacy or Purpose constraints found for {policy.resource_urn}'

		return '\n\n'.join(sql_statements)

	def _compile_opa(self, policy: ResolvedPolicy) -> dict:
		return self.rego_gen.build_bundle_data(policy)

	def _compile_iam(self, policy: ResolvedPolicy, context: dict) -> str:
		resource_arn = str(context.get('resource_arn', policy.resource_urn))
		return self.iam_gen.build_guardrail_policy(policy, resource_arn)

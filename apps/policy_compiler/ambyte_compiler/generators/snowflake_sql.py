from pathlib import Path

from ambyte_schemas.models.obligation import PrivacyMethod
from jinja2 import Environment, FileSystemLoader, select_autoescape


class SnowflakeGenerator:
	"""
	Translates high-level Privacy Rules into Snowflake Dynamic Masking
	and Row Access Policy SQL.
	"""

	def __init__(self, template_dir: Path):
		"""
		Args:
			template_dir: Path to 'policy-library/sql_templates'
		"""
		if not template_dir.exists():
			raise FileNotFoundError(f'Template directory not found: {template_dir}')

		self.env = Environment(
			loader=FileSystemLoader(str(template_dir)),
			autoescape=select_autoescape(default_for_string=False, default=False),
		)

	def _map_method_to_template_key(self, method: PrivacyMethod) -> str:
		"""
		Maps the Protocol Buffer Enum to the string expected by masking.sql
		"""
		mapping = {
			PrivacyMethod.PSEUDONYMIZATION: 'HASH',
			PrivacyMethod.ANONYMIZATION: 'FULL',
			PrivacyMethod.DIFFERENTIAL_PRIVACY: 'NOISE_INT',
			# Fallbacks
			PrivacyMethod.UNSPECIFIED: 'FULL',
			PrivacyMethod.ROW_LEVEL_SECURITY: 'FULL',  # RLS is handled by Row Access Policies, fallback to safe here
		}
		return mapping.get(method, 'FULL')

	def generate_masking_policy(
		self, policy_name: str, input_type: str, method: PrivacyMethod, allowed_roles: list[str], comment: str = ''
	) -> str:
		"""
		Generates a 'CREATE OR REPLACE MASKING POLICY' statement.
		Used for Column-level protection (PII redaction).
		"""
		template = self.env.get_template('masking.sql')

		template_method = self._map_method_to_template_key(method)

		return template.render(
			policy_name=policy_name,
			input_type=input_type,
			method=template_method,
			allowed_roles=allowed_roles,
			comment=comment,
		)

	def generate_row_access_policy(
		self,
		policy_name: str,
		input_type: str,
		ref_column: str,
		allowed_roles: list[str] | None = None,
		denied_roles: list[str] | None = None,
		denied_purposes: list[str] | None = None,
		comment: str = '',
	) -> str:
		"""
		Generates a 'CREATE OR REPLACE ROW ACCESS POLICY' statement.
		Used for Row-level protection (Purpose Limitation, Zero Trust).

		Args:
			policy_name: Name of the policy in Snowflake.
			input_type: The data type of the reference column (e.g. 'VARCHAR').
			ref_column: The name of the column used for binding (e.g. 'region_id').
			allowed_roles: List of roles that pass the Allowlist check.
			denied_roles: List of roles explicitly blocked.
			denied_purposes: List of strings (e.g. "MARKETING") to block in Session Tags.
			comment: Audit metadata.
		"""
		template = self.env.get_template('row_access.sql')

		# Normalize purposes to string tags for the SQL logic
		# e.g., denied_purposes=["MARKETING"] -> denied_tags=["marketing"]
		# The SQL template uses CONTAINS(LOWER(session), tag) so we normalize here.
		denied_tags = [p.lower() for p in (denied_purposes or [])]

		return template.render(
			policy_name=policy_name,
			input_type=input_type,
			ref_column=ref_column,
			allowed_roles=allowed_roles or [],
			denied_roles=denied_roles or [],
			denied_tags=denied_tags,
			comment=comment,
		)

	def generate_tag_binding(self, policy_name: str, tag_name: str) -> str:
		"""
		Generates the SQL to attach a masking policy to a Snowflake Tag.
		This enables 'Tag-Based Masking' where the policy follows the data classification.

		Args:
			policy_name: The name of the masking policy to apply.
			tag_name: The fully qualified name of the Snowflake Tag (e.g., 'admin.tags.pii').
		"""
		template = self.env.get_template('tag_binding.sql')

		return template.render(policy_name=policy_name, tag_name=tag_name)

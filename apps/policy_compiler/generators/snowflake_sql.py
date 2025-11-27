from pathlib import Path

from ambyte_schemas.models.obligation import PrivacyMethod
from jinja2 import Environment, FileSystemLoader, select_autoescape


class SnowflakeGenerator:
	"""
	Translates high-level Privacy Rules into Snowflake Dynamic Masking SQL.
	"""

	def __init__(self, template_dir: Path):
		"""
		    Args:
		template_dir: Path to 'policy-library/sql_templates'
		"""  # noqa: E101
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
			PrivacyMethod.ROW_LEVEL_SECURITY: 'FULL',  # RLS is handled elsewhere, fallback to safe
		}
		return mapping.get(method, 'FULL')

	def generate_masking_policy(
		self, policy_name: str, input_type: str, method: PrivacyMethod, allowed_roles: list[str], comment: str = ''
	) -> str:
		"""
		Generates a 'CREATE OR REPLACE MASKING POLICY' statement.
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

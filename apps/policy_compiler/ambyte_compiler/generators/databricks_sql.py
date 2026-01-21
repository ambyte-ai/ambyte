import logging
from pathlib import Path
from typing import Any

from ambyte_schemas.models.obligation import PrivacyMethod
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

logger = logging.getLogger(__name__)


class DatabricksGenerator:
	"""
	Translates Ambyte Policies into Databricks Unity Catalog SQL.
	Generates UDFs for Column Masks and Row Filters.
	"""

	def __init__(self, template_dir: Path):
		"""
		Args:
		    template_dir: Path to 'policy-library/sql_templates/databricks'
		"""  # noqa: E101
		if not template_dir.exists():
			raise FileNotFoundError(f'Template directory not found: {template_dir}')

		self.env = Environment(
			loader=FileSystemLoader(str(template_dir)),
			autoescape=select_autoescape(default_for_string=False, default=False),
			undefined=StrictUndefined,
		)

	def generate_masking_udf(
		self, policy_name: str, input_type: str, method: PrivacyMethod, allowed_groups: list[str], comment: str = ''
	) -> str:
		"""
		Generates a 'CREATE OR REPLACE FUNCTION' statement for Column Masking.
		"""
		template = self.env.get_template('masking.sql')

		# Map Ambyte Enum -> Template Key
		method_key = self._map_method_to_key(method)

		# Normalize Spark Types (e.g. VARCHAR -> STRING)
		spark_type = self._normalize_type(input_type)

		return template.render(
			policy_name=policy_name,
			input_type=spark_type,
			method=method_key,
			allowed_groups=allowed_groups,
			comment=comment,
		)

	def generate_row_filter_udf(
		self,
		policy_name: str,
		ref_column: str,
		input_type: str,
		allowed_groups: list[str] | None = None,
		denied_groups: list[str] | None = None,
		value_mapping: dict[str, list[str]] | None = None,
		comment: str = '',
	) -> str:
		"""
		Generates a 'CREATE OR REPLACE FUNCTION' statement for Row Filtering.
		"""
		template = self.env.get_template('row_filter.sql')

		spark_type = self._normalize_type(input_type)

		return template.render(
			policy_name=policy_name,
			ref_column=ref_column,
			input_type=spark_type,
			allowed_groups=allowed_groups or [],
			denied_groups=denied_groups or [],
			value_mapping=value_mapping or {},
			comment=comment,
		)

	def generate_binding_sql(
		self,
		table_name: str,
		mask_bindings: list[dict[str, str]] | None = None,
		row_filter_binding: dict[str, Any] | None = None,
	) -> str:
		"""
		Generates 'ALTER TABLE' statements to apply the functions.
		"""
		template = self.env.get_template('tag_binding.sql')

		return template.render(
			table_name=table_name, mask_bindings=mask_bindings or [], row_filter_binding=row_filter_binding
		)

	def _map_method_to_key(self, method: PrivacyMethod) -> str:
		"""Maps Protocol Buffer Enum to template string key."""
		mapping = {
			PrivacyMethod.PSEUDONYMIZATION: 'HASH',
			PrivacyMethod.ANONYMIZATION: 'FULL',
			PrivacyMethod.DIFFERENTIAL_PRIVACY: 'NOISE_INT',
			# Fallback
			PrivacyMethod.UNSPECIFIED: 'FULL',
		}
		# If method is an int (from protobuf), convert to Enum first if needed,
		# or handle directly if mapping keys are Enums. Here keys are Enums.
		# But method passed might be int if Pydantic model uses use_enum_values=True.

		if isinstance(method, int):
			try:
				method = PrivacyMethod(method)
			except ValueError:
				return 'FULL'

		return mapping.get(method, 'FULL')

	def _normalize_type(self, type_str: str) -> str:
		"""
		Maps generic or Snowflake types to Databricks Spark SQL types.
		"""
		t = type_str.upper()
		if 'VARCHAR' in t or 'TEXT' in t or 'CHAR' in t:
			return 'STRING'
		if 'NUMBER' in t or 'INTEGER' in t:
			return 'INT'  # or BIGINT based on precision, simple INT for now
		if 'BOOL' in t:
			return 'BOOLEAN'
		# Databricks supports ARRAY<T>, MAP<K,V>, STRUCT...
		# We assume complex types are passed correctly or handled as strings for now. # TODO
		return t

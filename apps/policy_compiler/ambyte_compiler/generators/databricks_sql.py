import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ambyte_schemas.models.obligation import PrivacyMethod
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

logger = logging.getLogger(__name__)

# Increment this when template logic changes in a way that requires re-deployment
# even if the input parameters haven't changed.
SCHEMA_VERSION = 1


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

	def _compute_content_hash(self, **kwargs: Any) -> str:
		"""
		Computes a deterministic hash of the semantic inputs to a UDF.

		This hash is embedded in the SQL COMMENT field and used by the enforcer
		to detect if an update is needed, avoiding false positives from Databricks
		reformatting the routine_definition.

		Returns:
		    A prefixed hash string like 'ambyte:v1:a3f8c2d1'
		"""  # noqa: E101
		# Sort keys for determinism, serialize to JSON for consistent representation
		canonical = json.dumps(kwargs, sort_keys=True, default=str)
		hash_digest = hashlib.sha256(canonical.encode()).hexdigest()[:8]
		return f'ambyte:v{SCHEMA_VERSION}:{hash_digest}'

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

		# Compute content hash for change detection
		content_hash = self._compute_content_hash(
			udf_type='mask',
			input_type=spark_type,
			method=method_key,
			allowed_groups=sorted(allowed_groups),
		)

		# Prepend hash to user-provided comment
		full_comment = f'{content_hash} | {comment}' if comment else content_hash

		return template.render(
			policy_name=policy_name,
			input_type=spark_type,
			method=method_key,
			allowed_groups=allowed_groups,
			comment=full_comment,
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

		# Normalize inputs for hashing
		allowed = sorted(allowed_groups or [])
		denied = sorted(denied_groups or [])
		# Sort value_mapping keys and their group lists for determinism
		sorted_mapping = {k: sorted(v) for k, v in sorted((value_mapping or {}).items())}

		# Compute content hash for change detection
		content_hash = self._compute_content_hash(
			udf_type='row_filter',
			ref_column=ref_column,
			input_type=spark_type,
			allowed_groups=allowed,
			denied_groups=denied,
			value_mapping=sorted_mapping,
		)

		# Prepend hash to user-provided comment
		full_comment = f'{content_hash} | {comment}' if comment else content_hash

		return template.render(
			policy_name=policy_name,
			ref_column=ref_column,
			input_type=spark_type,
			allowed_groups=allowed_groups or [],
			denied_groups=denied_groups or [],
			value_mapping=value_mapping or {},
			comment=full_comment,
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
		Maps generic SQL types to Databricks Spark SQL types.

		Handles:
		- Standard SQL types (VARCHAR, INTEGER, etc.)
		- Snowflake-specific types (NUMBER, TEXT, etc.)
		- Spark SQL complex types (ARRAY<T>, MAP<K,V>, STRUCT<...>)
		- Precision/scale specifications (DECIMAL(10,2), etc.)
		"""
		if not type_str:
			logger.warning('Empty type string provided, defaulting to STRING')
			return 'STRING'

		t = type_str.strip().upper()

		# ==================================================================
		# 1. STRING TYPES
		# ==================================================================
		if any(s in t for s in ['VARCHAR', 'TEXT', 'CHAR', 'CLOB', 'STRING']):
			return 'STRING'

		# ==================================================================
		# 2. NUMERIC TYPES - Integer Family
		# ==================================================================
		# BIGINT: 64-bit signed integer
		if 'BIGINT' in t or 'INT8' in t or 'LONG' in t:
			return 'BIGINT'

		# SMALLINT: 16-bit signed integer
		if 'SMALLINT' in t or 'INT2' in t:
			return 'SMALLINT'

		# TINYINT: 8-bit signed integer
		if 'TINYINT' in t or 'INT1' in t or 'BYTE' in t:
			return 'TINYINT'

		# INT: 32-bit signed integer (default for INTEGER/INT)
		if 'INT' in t:  # Matches INT, INTEGER, INT4
			return 'INT'

		# ==================================================================
		# 3. NUMERIC TYPES - Decimal/Float Family
		# ==================================================================
		# DECIMAL/NUMERIC with precision (preserve precision spec)
		if 'DECIMAL' in t or 'NUMERIC' in t or 'NUMBER' in t:
			# Preserve precision if specified: DECIMAL(10,2) -> DECIMAL(10,2)
			# Otherwise default to DECIMAL (Spark default precision)
			import re

			precision_match = re.search(r'\([\d,\s]+\)', t)
			if precision_match:
				return f'DECIMAL{precision_match.group()}'
			return 'DECIMAL'

		# DOUBLE: 64-bit floating point
		if 'DOUBLE' in t or 'FLOAT8' in t:
			return 'DOUBLE'

		# FLOAT: 32-bit floating point
		if 'FLOAT' in t or 'REAL' in t or 'FLOAT4' in t:
			return 'FLOAT'

		# ==================================================================
		# 4. BOOLEAN
		# ==================================================================
		if 'BOOL' in t:
			return 'BOOLEAN'

		# ==================================================================
		# 5. DATE/TIME TYPES
		# ==================================================================
		if 'TIMESTAMP' in t:
			# Spark has TIMESTAMP and TIMESTAMP_NTZ (no timezone)
			if 'NTZ' in t or 'WITHOUT' in t:
				return 'TIMESTAMP_NTZ'
			return 'TIMESTAMP'

		if 'DATE' in t:
			return 'DATE'

		if 'TIME' in t and 'STAMP' not in t:
			# Spark doesn't have TIME type, use STRING for time-only values
			logger.warning(f"TIME type '{type_str}' not supported in Spark, using STRING")
			return 'STRING'

		if 'INTERVAL' in t:
			return 'INTERVAL'

		# ==================================================================
		# 6. BINARY TYPES
		# ==================================================================
		if 'BINARY' in t or 'VARBINARY' in t or 'BLOB' in t or 'BYTES' in t:
			return 'BINARY'

		# ==================================================================
		# 7. COMPLEX TYPES - Already Spark format, normalize case
		# ==================================================================
		# ARRAY<element_type>
		if t.startswith('ARRAY'):
			# Recursively normalize the element type
			match = self._extract_complex_type_params(type_str)
			if match:
				inner_type = self._normalize_type(match)
				return f'ARRAY<{inner_type}>'
			return 'ARRAY<STRING>'  # Fallback

		# MAP<key_type, value_type>
		if t.startswith('MAP'):
			match = self._extract_complex_type_params(type_str)
			if match and ',' in match:
				parts = match.split(',', 1)
				key_type = self._normalize_type(parts[0].strip())
				val_type = self._normalize_type(parts[1].strip())
				return f'MAP<{key_type},{val_type}>'
			return 'MAP<STRING,STRING>'  # Fallback

		# STRUCT<field:type, ...>
		if t.startswith('STRUCT'):
			# STRUCT types are complex; pass through with case normalization
			# Full parsing would require recursive handling of nested fields
			return type_str.upper()

		# ==================================================================
		# 8. VARIANT (Databricks-specific semi-structured)
		# ==================================================================
		if 'VARIANT' in t or 'JSON' in t:
			# Databricks uses STRING for JSON, VARIANT is Unity Catalog specific
			return 'STRING'

		# ==================================================================
		# 9. UNRECOGNIZED - Log and pass through
		# ==================================================================
		logger.debug(f"Unrecognized type '{type_str}', passing through as-is")
		return t

	def _extract_complex_type_params(self, type_str: str) -> str | None:
		"""
		Extracts the inner parameters from complex types.
		E.g., 'ARRAY<STRING>' -> 'STRING'
		      'MAP<STRING, INT>' -> 'STRING, INT'
		"""  # noqa: E101
		import re

		match = re.search(r'<(.+)>$', type_str, re.IGNORECASE)
		return match.group(1) if match else None

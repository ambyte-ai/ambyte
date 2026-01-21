import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import sqlparse
from ambyte_schemas.models.artifact import PolicyBundle
from pydantic import ValidationError


@dataclass
class ValidationResult:
	"""
	Holds the outcome of a validation check.
	"""

	is_valid: bool
	errors: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)

	def add_error(self, msg: str):
		self.is_valid = False
		self.errors.append(msg)

	def add_warning(self, msg: str):
		self.warnings.append(msg)


class ArtifactValidator(ABC):
	"""
	Abstract base class for all target-specific validators.
	"""

	@abstractmethod
	def validate(self, artifact: str | dict[str, Any]) -> ValidationResult:
		"""
		Validates the generated artifact.

		Args:
		    artifact: The output from a generator (SQL string, JSON string, or Dict).

		Returns:
		    ValidationResult object.
		"""  # noqa: E101
		pass


# ==============================================================================
# SNOWFLAKE SQL VALIDATOR
# ==============================================================================


class SnowflakeSqlValidator(ArtifactValidator):
	"""
	Validates Snowflake SQL statements.
	Checks for:
	1. Jinja rendering errors (undefined variables).
	2. Basic SQL syntax structure.
	3. Dangerous keywords.
	4. Unbalanced parentheses.
	"""

	DANGEROUS_KEYWORDS = ['DROP TABLE', 'DROP DATABASE', 'GRANT ACCOUNTADMIN', 'DELETE FROM']

	def validate(self, artifact: str | dict) -> ValidationResult:
		result = ValidationResult(is_valid=True)

		# SQL should be a string
		if not isinstance(artifact, str):
			result.add_error(f'Expected SQL string, got {type(artifact)}')
			return result

		if not artifact.strip():
			# Empty artifact might be valid if no policies apply, but usually worth a warning
			result.add_warning('Generated SQL is empty.')
			return result

		# 1. Check for Jinja Leakage (Undefined variables often appear as empty strings or None)
		# Note: 'None' in SQL can be valid (NULL), but 'None' string literal from Python is suspicious
		# We look for unrendered tags
		if '{{' in artifact or '}}' in artifact or '{%' in artifact:
			result.add_error('Found unrendered Jinja tags ({{ or {%}). Template rendering failed.')

		if 'UNDEFINED' in artifact:
			result.add_error("Found 'UNDEFINED' in SQL. Verify template variables.")

		# 2. Check for Dangerous Keywords
		upper_sql = artifact.upper()
		for kw in self.DANGEROUS_KEYWORDS:
			if kw in upper_sql:
				# We flag this as an error because policy compilers shouldn't be dropping tables
				result.add_error(f"Dangerous keyword detected: '{kw}'")

		# 3. Check Unbalanced Parentheses (Simple heuristic)
		if upper_sql.count('(') != upper_sql.count(')'):
			result.add_error('Unbalanced parentheses detected in SQL.')

		# 4. sqlparse Structure Check
		try:
			parsed = sqlparse.parse(artifact)
			if not parsed:
				result.add_error('SQL parsing failed: No statements found.')

			# Check that we typically have CREATE, ALTER, or COMMENT statements
			allowed_types = ('CREATE', 'ALTER', 'COMMENT')
			for stmt in parsed:
				type_str = stmt.get_type().upper()
				if type_str != 'UNKNOWN' and type_str not in allowed_types:
					result.add_warning(f"Unexpected statement type '{type_str}'. Expected CREATE, ALTER, or COMMENT.")
		except Exception as e:
			result.add_error(f'SQL syntax check failed: {str(e)}')

		return result


# ==============================================================================
# DATABRICKS SQL VALIDATOR
# ==============================================================================


class DatabricksSqlValidator(ArtifactValidator):
	"""
	Validates Databricks Unity Catalog SQL statements.
	Checks for:
	1. Jinja rendering errors.
	2. Basic SQL syntax structure.
	3. Dangerous keywords (e.g. DROP CATALOG).
	4. Unbalanced parentheses.
	"""

	DANGEROUS_KEYWORDS = [
		'DROP CATALOG',
		'DROP SCHEMA',
		'DROP TABLE',
		'DROP VIEW',
		'DROP FUNCTION',
		'DELETE FROM',
		'GRANT ADMIN',
	]

	def validate(self, artifact: str | dict) -> ValidationResult:
		result = ValidationResult(is_valid=True)

		if not isinstance(artifact, str):
			result.add_error(f'Expected SQL string, got {type(artifact)}')
			return result

		if not artifact.strip():
			result.add_warning('Generated Databricks SQL is empty.')
			return result

		# 1. Check for Jinja Leakage
		if '{{' in artifact or '}}' in artifact or '{%' in artifact:
			result.add_error('Found unrendered Jinja tags. Template rendering failed.')

		if 'UNDEFINED' in artifact:
			result.add_error("Found 'UNDEFINED' in SQL. Verify template variables.")

		# 2. Check for Dangerous Keywords
		upper_sql = artifact.upper()
		for kw in self.DANGEROUS_KEYWORDS:
			if kw in upper_sql:
				result.add_error(f"Dangerous keyword detected: '{kw}'")

		# 3. Check Unbalanced Parentheses
		if upper_sql.count('(') != upper_sql.count(')'):
			result.add_error('Unbalanced parentheses detected in SQL.')

		# 4. sqlparse Structure Check
		try:
			parsed = sqlparse.parse(artifact)
			if not parsed:
				result.add_error('SQL parsing failed: No statements found.')

			# We expect CREATE FUNCTION or ALTER TABLE usually
			allowed_types = ('CREATE', 'ALTER', 'COMMENT', 'SELECT')
			for stmt in parsed:
				type_str = stmt.get_type().upper()
				if type_str != 'UNKNOWN' and type_str not in allowed_types:
					result.add_warning(f"Unexpected statement type '{type_str}'. Expected CREATE, ALTER, or COMMENT.")
		except Exception as e:
			result.add_error(f'SQL syntax check failed: {str(e)}')

		return result


# ==============================================================================
# IAM POLICY VALIDATOR
# ==============================================================================


class IamJsonValidator(ArtifactValidator):
	"""
	Validates AWS IAM Policy Documents (JSON).
	Checks for:
	1. Valid JSON syntax.
	2. Required IAM fields (Version, Statement).
	3. AWS-specific constraints (Sid regex, Effect Enum).
	"""

	SID_REGEX = re.compile(r'^[a-zA-Z0-9]+$')

	def validate(self, artifact: str | dict) -> ValidationResult:
		result = ValidationResult(is_valid=True)

		# 1. Parse JSON
		try:
			data = artifact if isinstance(artifact, dict) else json.loads(str(artifact))
		except json.JSONDecodeError as e:
			result.add_error(f'Invalid JSON format: {e}')
			return result

		# 2. Structure Check
		if 'Version' not in data:
			result.add_error("IAM Policy missing 'Version' field.")

		if 'Statement' not in data:
			result.add_error("IAM Policy missing 'Statement' field.")
			return result  # Cannot proceed

		if not isinstance(data['Statement'], list):
			result.add_error("'Statement' must be a list.")
			return result

		# 3. Statement Checks
		for idx, stmt in enumerate(data['Statement']):
			# Sid Validation
			if 'Sid' in stmt:
				if not self.SID_REGEX.match(stmt['Sid']):
					result.add_error(f"Statement {idx}: Sid '{stmt['Sid']}' must be alphanumeric.")

			# Effect Validation
			if 'Effect' not in stmt:
				result.add_error(f"Statement {idx}: Missing 'Effect'.")
			elif stmt['Effect'] not in ('Allow', 'Deny'):
				result.add_error(f"Statement {idx}: Effect must be 'Allow' or 'Deny'.")

			# Action/Resource Validation
			if 'Action' not in stmt and 'NotAction' not in stmt:
				result.add_error(f"Statement {idx}: Must contain 'Action' or 'NotAction'.")

			if 'Resource' not in stmt and 'NotResource' not in stmt:
				result.add_error(f"Statement {idx}: Must contain 'Resource' or 'NotResource'.")

		return result


# ==============================================================================
# OPA BUNDLE VALIDATOR
# ==============================================================================


class OpaDataValidator(ArtifactValidator):
	"""
	Validates the Data Dictionary generated for OPA.
	"""

	def validate(self, artifact: str | dict) -> ValidationResult:
		result = ValidationResult(is_valid=True)

		try:
			data = artifact if isinstance(artifact, dict) else json.loads(str(artifact))
		except json.JSONDecodeError as e:
			result.add_error(f'Invalid JSON format: {e}')
			return result

		# Basic Schema Check
		if 'resource_urn' not in data:
			result.add_error("OPA Bundle missing 'resource_urn'.")

		if 'meta' not in data:
			result.add_warning("OPA Bundle missing 'meta' information.")

		# Check for empty policies (if no keys exist besides urn and meta)
		# We assume strict keys: 'retention', 'geofencing', etc.
		policy_keys = {'retention', 'geofencing', 'ai_rules', 'purpose', 'privacy'}
		if not any(k in data for k in policy_keys):
			result.add_warning(f'OPA Bundle for {data.get("resource_urn")} has no active constraints.')

		return result


# ==============================================================================
# LOCAL PYTHON BUNDLE VALIDATOR
# ==============================================================================


class LocalBundleValidator(ArtifactValidator):
	"""
	Validates the local_policies.json bundle by attempting to load it
	back into the official Pydantic Schema.
	"""

	def validate(self, artifact: str | dict) -> ValidationResult:
		result = ValidationResult(is_valid=True)

		json_str = json.dumps(artifact) if isinstance(artifact, dict) else str(artifact)

		try:
			# The ultimate test: Can the SDK actually load this?
			PolicyBundle.model_validate_json(json_str)
		except ValidationError as e:
			result.is_valid = False
			# Format Pydantic errors for readability
			for err in e.errors():
				loc = ' -> '.join(str(loc_part) for loc_part in err['loc'])
				result.errors.append(f"Schema Error at '{loc}': {err['msg']}")
		except Exception as e:
			result.add_error(f'Unexpected bundle error: {str(e)}')

		return result

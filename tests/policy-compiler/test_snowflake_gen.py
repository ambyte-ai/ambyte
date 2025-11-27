from ambyte_schemas.models.obligation import PrivacyMethod
from policy_compiler.generators.snowflake_sql import SnowflakeGenerator


def test_snowflake_generator_hash(policy_library_path):
	# Initialize Generator pointing to the fixture path
	gen = SnowflakeGenerator(template_dir=policy_library_path / 'sql_templates')

	sql = gen.generate_masking_policy(
		policy_name='mask_email_hash',
		input_type='VARCHAR',
		method=PrivacyMethod.PSEUDONYMIZATION,
		allowed_roles=['HR_ADMIN', 'COMPLIANCE_OFFICER'],
		comment='GDPR Art 32',
	)

	# Assertions on generated SQL
	assert 'CREATE OR REPLACE MASKING POLICY mask_email_hash' in sql
	assert 'AS (val VARCHAR)' in sql
	assert 'SHA2(CAST(val AS VARCHAR), 256)' in sql  # The HASH logic
	assert "'HR_ADMIN', 'COMPLIANCE_OFFICER'" in sql  # The Role allowlist
	assert "COMMENT ON MASKING POLICY mask_email_hash IS 'GDPR Art 32'" in sql


def test_snowflake_generator_full_redaction(policy_library_path):
	gen = SnowflakeGenerator(template_dir=policy_library_path / 'sql_templates')

	sql = gen.generate_masking_policy(
		policy_name='mask_secret', input_type='NUMBER', method=PrivacyMethod.ANONYMIZATION, allowed_roles=[]
	)

	assert 'RETURNS NUMBER' in sql
	assert 'NULL' in sql  # Full redaction for numbers defaults to NULL in our template

import pytest
from ambyte_schemas.models.obligation import PrivacyMethod

from apps.policy_compiler.ambyte_compiler.generators.snowflake_sql import SnowflakeGenerator

# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_template_dir(tmp_path):
	"""
	Creates a temporary directory populated with the required SQL templates.
	This ensures tests pass even if the physical files aren't in policy-library yet.
	"""
	sql_dir = tmp_path / 'sql_templates'
	sql_dir.mkdir()

	# 1. Masking Template (Simplified for testing)
	(sql_dir / 'masking.sql').write_text("""
    CREATE OR REPLACE MASKING POLICY {{ policy_name }} AS (val {{ input_type }}) RETURNS {{ input_type }} ->
        CASE
            WHEN CURRENT_ROLE() IN ({% for role in allowed_roles %}'{{ role }}'{% if not loop.last %}, {% endif %}{% endfor %}) THEN val
            {% if method == 'HASH' %}ELSE SHA2(val){% else %}ELSE NULL{% endif %}
        END;
    COMMENT ON MASKING POLICY {{ policy_name }} IS '{{ comment }}';
    """)  # noqa: E501

	# 2. Row Access Template
	(sql_dir / 'row_access.sql').write_text("""
    CREATE OR REPLACE ROW ACCESS POLICY {{ policy_name }} AS ({{ ref_column }} {{ input_type }}) RETURNS BOOLEAN ->
        CASE
            {% if denied_tags %}
            WHEN (
                {% for tag in denied_tags %}
                CONTAINS(LOWER(NVL(CURRENT_SESSION(), '')), '{{ tag }}'){% if not loop.last %} OR {% endif %}
                {% endfor %}
            ) THEN FALSE
            {% endif %}
            
            {% if denied_roles %}
            WHEN CURRENT_ROLE() IN ({% for role in denied_roles %}'{{ role }}'{% if not loop.last %}, {% endif %}{% endfor %}) THEN FALSE
            {% endif %}

            {% if allowed_roles %}
            WHEN CURRENT_ROLE() IN ({% for role in allowed_roles %}'{{ role }}'{% if not loop.last %}, {% endif %}{% endfor %}) THEN TRUE
            {% endif %}
            
            ELSE FALSE
        END;
    """)  # noqa: E501, E101

	# 3. Tag Binding Template
	(sql_dir / 'tag_binding.sql').write_text("""
    ALTER TAG {{ tag_name }} SET MASKING POLICY {{ policy_name }};
    """)  # noqa: E501, E101

	return sql_dir


@pytest.fixture
def generator(mock_template_dir):
	return SnowflakeGenerator(template_dir=mock_template_dir)


# ==============================================================================
# EXISTING MASKING TESTS
# ==============================================================================


def test_snowflake_generator_hash(generator):
	sql = generator.generate_masking_policy(
		policy_name='mask_email_hash',
		input_type='VARCHAR',
		method=PrivacyMethod.PSEUDONYMIZATION,
		allowed_roles=['HR_ADMIN', 'COMPLIANCE_OFFICER'],
		comment='GDPR Art 32',
	)

	assert 'CREATE OR REPLACE MASKING POLICY mask_email_hash' in sql
	assert 'SHA2(val)' in sql
	assert "'HR_ADMIN', 'COMPLIANCE_OFFICER'" in sql
	assert "COMMENT ON MASKING POLICY mask_email_hash IS 'GDPR Art 32'" in sql


def test_snowflake_generator_full_redaction(generator):
	sql = generator.generate_masking_policy(
		policy_name='mask_secret', input_type='NUMBER', method=PrivacyMethod.ANONYMIZATION, allowed_roles=[]
	)
	assert 'ELSE NULL' in sql


# ==============================================================================
# ROW ACCESS & TAG BINDING TESTS
# ==============================================================================


def test_generate_row_access_purpose_limitation(generator):
	"""
	Verifies that 'denied_purposes' are correctly normalized to lower-case tags
	and injected into the session check logic.
	"""
	sql = generator.generate_row_access_policy(
		policy_name='rap_marketing_block',
		input_type='VARCHAR',
		ref_column='region_id',
		allowed_roles=['ADMIN'],
		denied_purposes=['MARKETING', 'Sales_Outreach'],  # Mixed case input
		comment='Block secondary usage',
	)

	# 1. Structure Check
	assert 'CREATE OR REPLACE ROW ACCESS POLICY rap_marketing_block' in sql
	assert 'AS (region_id VARCHAR)' in sql

	# 2. Purpose -> Tag Conversion Logic
	# The generator should lowercase "MARKETING" -> "marketing"
	assert "CONTAINS(LOWER(NVL(CURRENT_SESSION(), '')), 'marketing')" in sql
	assert "CONTAINS(LOWER(NVL(CURRENT_SESSION(), '')), 'sales_outreach')" in sql

	# 3. Allowlist Check
	assert "'ADMIN'" in sql


def test_generate_row_access_role_blocking(generator):
	"""
	Verifies that explicit 'denied_roles' generate a blocking WHEN clause.
	"""
	sql = generator.generate_row_access_policy(
		policy_name='rap_intern_block',
		input_type='NUMBER',
		ref_column='id',
		denied_roles=['INTERN', '3RD_PARTY_VENDOR'],
	)

	assert "WHEN CURRENT_ROLE() IN ('INTERN', '3RD_PARTY_VENDOR') THEN FALSE" in sql


def test_generate_tag_binding(generator):
	"""
	Verifies the generation of ALTER TAG statements.
	"""
	sql = generator.generate_tag_binding(policy_name='mask_pii_email', tag_name='AMBYTE_GOVERNANCE.TAGS.PII_CATEGORY')

	assert 'ALTER TAG AMBYTE_GOVERNANCE.TAGS.PII_CATEGORY SET MASKING POLICY mask_pii_email;' in sql

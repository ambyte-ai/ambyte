import os

# ==============================================================================
# TEST COLLECTION ENVIRONMENT VARIABLES
# ==============================================================================
# We must set these before pytest collects the test files to prevent Pydantic 
# from throwing ValidationErrors when files import `settings` at the module level.
_TEST_ENV_VARS = {
	'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
	'AMBYTE_DATABRICKS_TOKEN': 'dapi_test_token',
	'AMBYTE_DATABRICKS_WAREHOUSE_ID': 'wh_123456789',
	'AMBYTE_API_KEY': 'sk_test_mock_key',
	'AMBYTE_DATABRICKS_CONTROL_PLANE_URL': 'http://mock-api.ambyte.local',
	'AMBYTE_DATABRICKS_LOCAL_MODE': 'false',
	'AMBYTE_DATABRICKS_GOVERNANCE_CATALOG': 'main',
	'AMBYTE_DATABRICKS_GOVERNANCE_SCHEMA': 'ambyte_gov',
}
for k, v in _TEST_ENV_VARS.items():
	os.environ.setdefault(k, v)

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from ambyte_schemas.models.common import (
	Actor,
	ActorType,
	ResourceIdentifier,
	SensitivityLevel,
)
from ambyte_schemas.models.dataset import (
	Dataset,
	DataSubjectType,
	LicenseInfo,
	PiiCategory,
	SchemaField,
)
from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import CatalogInfo, ColumnInfo, ColumnTypeName, SchemaInfo, TableInfo, TableType
from databricks.sdk.service.sql import (
	ColumnInfo as SqlColumnInfo,
)
from databricks.sdk.service.sql import (
	ResultData,
	ResultManifest,
	ResultSchema,
	StatementResponse,
	StatementState,
	StatementStatus,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ==============================================================================
# PATH & CONFIG FIXTURES
# ==============================================================================


@pytest.fixture(scope='session')
def project_root() -> Path:
	"""Returns the root directory of the repository."""
	return Path(__file__).parent.parent


@pytest.fixture(scope='session')
def policy_library_path(project_root) -> Path:
	return project_root / 'policy-library'


@pytest.fixture(scope='session')
def ontology_path(project_root) -> Path:
	return project_root / 'schemas' / 'ontology' / 'regulations'


# ==============================================================================
# COMPILER / TEMPLATE FIXTURES
# ==============================================================================


@pytest.fixture(scope='session')
def jinja_sql_env(policy_library_path) -> Environment:
	"""
	Sets up a Jinja2 environment pointing to the SQL templates directory.
	Used for testing apps/policy-compiler logic.
	"""
	template_dir = policy_library_path / 'sql_templates'
	if not template_dir.exists():
		pytest.fail(f'SQL Template directory not found at: {template_dir}')

	return Environment(loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape())


@pytest.fixture(scope='session')
def ontology_data(ontology_path) -> dict:
	"""
	Loads both GDPR and AI Act mappings into a dictionary for validation tests.
	"""
	data = {}
	files = ['gdpr_mappings.yaml', 'ai_act_mappings.yaml']

	for filename in files:
		file_path = ontology_path / filename
		if file_path.exists():
			with open(file_path) as f:
				data[filename] = yaml.safe_load(f)
		else:
			pytest.fail(f'Ontology file missing: {filename}')

	return data


# ==============================================================================
# SCHEMA MODEL FACTORIES
# ==============================================================================


@pytest.fixture
def sample_actor() -> Actor:
	"""Creates a basic Human Actor."""
	return Actor(id='user_123', type=ActorType.HUMAN, roles=['DATA_SCIENTIST', 'VIEWER'], attributes={'location': 'EU'})


@pytest.fixture
def sample_resource() -> ResourceIdentifier:
	return ResourceIdentifier(
		platform='snowflake', location='prod_db.sales.customers', native_id='arn:aws:snowflake:...'
	)


@pytest.fixture
def sample_dataset(sample_actor, sample_resource) -> Dataset:
	"""
	Creates a fully populated Dataset object with PII fields.
	Useful for testing serialization and proto conversion.
	"""
	return Dataset(
		id='ds_uuid_999',
		urn='urn:ambyte:snowflake:prod_db:sales:customers',
		name='Customer Churn Data',
		description='Historical customer data for churn prediction.',
		owner=sample_actor,
		resource=sample_resource,
		sensitivity=SensitivityLevel.CONFIDENTIAL,
		geo_region='DE',
		data_subjects=[DataSubjectType.CUSTOMER],
		license=LicenseInfo(spdx_id='Proprietary'),
		created_at=datetime.now(timezone.utc),
		updated_at=datetime.now(timezone.utc),
		fields=[
			SchemaField(name='email', native_type='VARCHAR', is_pii=True, pii_category=PiiCategory.EMAIL_ADDRESS),
			SchemaField(name='subscription_tier', native_type='VARCHAR', is_pii=False),
		],
	)


@pytest.fixture
def sample_obligation_retention() -> Obligation:
	"""
	Creates an Obligation with a Retention Rule.
	"""
	return Obligation(
		id='obl_gdpr_art_17',
		title='Right to Erasure',
		description='Delete data upon request or expiry.',
		provenance=SourceProvenance(source_id='GDPR', document_type='REGULATION', section_reference='Art 17'),
		enforcement_level=EnforcementLevel.BLOCKING,
		# OneOf Constraint: Retention
		retention=RetentionRule(
			duration=timedelta(days=365), trigger=RetentionTrigger.EVENT_DATE, allow_legal_hold_override=True
		),
	)


@pytest.fixture
def sample_obligation_geofencing() -> Obligation:
	"""
	Creates an Obligation with a Geofencing Rule.
	"""
	return Obligation(
		id='obl_gdpr_transfer',
		title='Cross Border Transfer',
		description='Keep data in EU/EEA or adequate countries.',
		provenance=SourceProvenance(source_id='GDPR', document_type='REGULATION', section_reference='Art 44'),
		enforcement_level=EnforcementLevel.BLOCKING,
		# OneOf Constraint: Geofencing
		geofencing=GeofencingRule(allowed_regions=['DE', 'FR', 'IT'], strict_residency=True),
	)


# ==============================================================================
# CLI AUTHENTICATION MOCKS
# ==============================================================================


@pytest.fixture
def mock_credentials_path(tmp_path):
	"""
	Creates a temporary directory structure to mimic ~/.ambyte
	"""
	mock_home = tmp_path / 'fake_home'
	ambyte_dir = mock_home / '.ambyte'
	ambyte_dir.mkdir(parents=True)
	return ambyte_dir


@pytest.fixture
def mock_credentials_file(mock_credentials_path, monkeypatch):
	"""
	Redirects the CLI auth service to a temporary credentials file.
	Returns a factory function to easily set up different auth states.
	"""
	creds_file = mock_credentials_path / 'credentials'

	# Patch the constants in the auth service module so it looks at our temp file
	import ambyte_cli.services.auth as auth_svc

	monkeypatch.setattr(auth_svc, 'AMBYTE_HOME', mock_credentials_path)
	monkeypatch.setattr(auth_svc, 'CREDENTIALS_FILE', creds_file)

	def _setup_creds(
		api_key: str = 'sk_live_test_key_12345',
		project_id: str = '00000000-0000-0000-0000-000000000001',
		org_id: str = '00000000-0000-0000-0000-000000000002',
		profile: str = 'default',
	):
		data = {
			profile: {
				'api_key': api_key,
				'project_id': project_id,
				'organization_id': org_id,
			}
		}
		with open(creds_file, 'w', encoding='utf-8') as f:
			yaml.dump(data, f)
		return creds_file

	return _setup_creds


@pytest.fixture
def no_credentials(mock_credentials_path, monkeypatch):
	"""
	Ensures the credentials file does not exist for testing logged-out states.
	"""
	creds_file = mock_credentials_path / 'credentials'
	if creds_file.exists():
		creds_file.unlink()

	import ambyte_cli.services.auth as auth_svc

	monkeypatch.setattr(auth_svc, 'CREDENTIALS_FILE', creds_file)
	return creds_file


@pytest.fixture(autouse=True)
def mock_env_vars():
	"""
	Sets up valid environment variables for all tests to prevent
	Settings validation errors on import or instantiation.
	"""
	env_vars = {
		'AMBYTE_DATABRICKS_HOST': 'https://test.databricks.com',
		'AMBYTE_DATABRICKS_TOKEN': 'dapi_test_token',
		'AMBYTE_DATABRICKS_WAREHOUSE_ID': 'wh_123456789',
		'AMBYTE_API_KEY': 'sk_test_mock_key',
		'AMBYTE_DATABRICKS_CONTROL_PLANE_URL': 'http://mock-api.ambyte.local',
		'AMBYTE_DATABRICKS_LOCAL_MODE': 'false',
		# Explicitly set defaults to ensure deterministic behavior
		'AMBYTE_DATABRICKS_GOVERNANCE_CATALOG': 'main',
		'AMBYTE_DATABRICKS_GOVERNANCE_SCHEMA': 'ambyte_gov',
	}
	with patch.dict(os.environ, env_vars):
		from ambyte_databricks import config

		# Reset and recreate the lazy singleton with test env vars
		config.reset_settings()
		config._settings = config.Settings()
		yield
		# Clean up: reset the singleton so it doesn't leak between tests
		config.reset_settings()


# ==============================================================================
# DATABRICKS CLIENT MOCK
# ==============================================================================


@pytest.fixture
def mock_db_client():
	"""
	Returns a mocked Databricks WorkspaceClient.
	Wraps all sub-services used by the connector.
	"""
	client = MagicMock(spec=WorkspaceClient)

	# Mock Sub-services
	client.catalogs = MagicMock()
	client.schemas = MagicMock()
	client.tables = MagicMock()
	client.functions = MagicMock()
	client.statement_execution = MagicMock()
	client.entity_tag_assignments = MagicMock()

	return client


# ==============================================================================
# FACTORY HELPERS
# ==============================================================================


@pytest.fixture
def make_catalog():
	def _make(name: str):
		return CatalogInfo(name=name)

	return _make


@pytest.fixture
def make_schema():
	def _make(name: str, catalog_name: str):
		return SchemaInfo(name=name, catalog_name=catalog_name)

	return _make


@pytest.fixture
def make_table():
	def _make(
		name: str,
		schema: str,
		catalog: str,
		columns: list[dict[str, str]] | None = None,
		table_type: TableType = TableType.MANAGED,
	):
		full_name = f'{catalog}.{schema}.{name}'

		cols = []
		if columns:
			for c in columns:
				cols.append(
					ColumnInfo(
						name=c.get('name'),
						type_text=c.get('type', 'STRING'),
						type_name=ColumnTypeName.STRING,  # Simplified
						position=0,
					)
				)

		return TableInfo(
			name=name,
			catalog_name=catalog,
			schema_name=schema,
			full_name=full_name,
			table_type=table_type,
			columns=cols,
			owner='test_owner',
			storage_location=f's3://bucket/{name}',
			created_at=123456789,
			updated_at=123456789,
		)

	return _make


@pytest.fixture
def mock_sql_response():
	"""
	Helper to generate a successful SQL execution response structure.
	"""

	def _make(
		statement_id: str = 'stmt_123',
		state: StatementState = StatementState.SUCCEEDED,
		data: list[list[Any]] | None = None,
		columns: list[str] | None = None,
	):
		# 1. Manifest / Schema
		manifest = None
		if columns:
			cols = [SqlColumnInfo(name=c, position=i) for i, c in enumerate(columns)]
			manifest = ResultManifest(schema=ResultSchema(columns=cols))

		# 2. Result Data
		result = None
		if data is not None:
			# Databricks returns data as string arrays usually
			str_data = [[str(item) for item in row] for row in data]
			result = ResultData(chunk_index=0, row_count=len(data), data_array=str_data)

		return StatementResponse(
			statement_id=statement_id, status=StatementStatus(state=state), manifest=manifest, result=result
		)

	return _make

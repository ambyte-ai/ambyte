"""
Defines the structure of the local project configuration (.ambyte/config.yaml)
and handles loading/saving logic.
"""

import sys
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError

# Constants
CONFIG_DIR_NAME = '.ambyte'
CONFIG_FILE_NAME = 'config.yaml'
DEFAULT_POLICIES_DIR = 'policies'
DEFAULT_ARTIFACTS_DIR = '.ambyte/dist'
DEFAULT_RESOURCES_DIR = 'resources'


class TargetPlatform(StrEnum):
	"""
	Supported compilation targets.
	Matches apps/policy_compiler/ambyte_compiler/service.py
	"""

	LOCAL = 'local'  # JSON artifact for Python SDK
	SNOWFLAKE = 'snowflake'  # SQL Dynamic Masking Policies
	OPA = 'opa'  # Rego data bundles
	AWS_IAM = 'aws_iam'  # JSON Identity Policies
	DATABRICKS = 'databricks'  # SQL Dynamic Masking Policies


class CloudConfig(BaseModel):
	"""
	Configuration for connecting to the Ambyte Control Plane.
	Note: Secrets (API Keys) are NOT stored here; they go in ~/.ambyte/credentials.
	"""

	url: HttpUrl = Field(default=HttpUrl('https://api.ambyte.ai'), description='API Base URL')
	organization_id: str | None = Field(default=None, description='The Org ID this workspace belongs to.')
	project_id: str | None = Field(default=None, description='The specific Project ID.')


class AmbyteConfig(BaseModel):
	"""
	The root schema for .ambyte/config.yaml
	"""

	version: str = Field(default='1.0', description='Config schema version')
	project_name: str = Field(..., description='Human-readable name of this data project')

	# Paths (relative to project root)
	policies_dir: Path = Field(
		default=Path(DEFAULT_POLICIES_DIR), description='Directory containing source YAML obligations.'
	)
	artifacts_dir: Path = Field(
		default=Path(DEFAULT_ARTIFACTS_DIR), description='Directory where compiled outputs are written.'
	)
	resources_dir: Path = Field(
		default=Path(DEFAULT_RESOURCES_DIR), description='Directory containing resource inventory files.'
	)

	# Compilation Settings
	targets: list[TargetPlatform] = Field(
		default=[TargetPlatform.LOCAL], description='List of platforms to generate artifacts for.'
	)

	# Cloud settings
	cloud: CloudConfig = Field(default_factory=CloudConfig)

	@property
	def abs_policies_dir(self) -> Path:
		"""Returns the absolute path to the policies directory."""
		return get_workspace_root() / self.policies_dir

	@property
	def abs_artifacts_dir(self) -> Path:
		"""Returns the absolute path to the artifacts directory."""
		return get_workspace_root() / self.artifacts_dir

	@property
	def abs_resources_dir(self) -> Path:
		"""Returns the absolute path to the resources directory."""
		return get_workspace_root() / self.resources_dir


# ==============================================================================
# Helper Functions
# ==============================================================================


def get_workspace_root() -> Path:
	"""
	Traverses up from CWD to find the directory containing .ambyte/.
	Raises FileNotFoundError if not found.
	"""
	cwd = Path.cwd()

	# Check current and parents
	for path in [cwd, *cwd.parents]:
		if (path / CONFIG_DIR_NAME).exists() and (path / CONFIG_DIR_NAME).is_dir():
			return path

	raise FileNotFoundError("Could not find .ambyte directory. Run 'ambyte init' first.")


def load_config() -> AmbyteConfig:
	"""
	Locates and parses the config.yaml file.
	Exits the CLI gracefully if invalid.
	"""
	try:
		root = get_workspace_root()
		config_path = root / CONFIG_DIR_NAME / CONFIG_FILE_NAME

		if not config_path.exists():
			# Should be caught by get_workspace_root usually, but double check
			raise FileNotFoundError(f'Config file missing at {config_path}')

		with open(config_path, encoding='utf-8') as f:
			data = yaml.safe_load(f) or {}

		return AmbyteConfig.model_validate(data)

	except FileNotFoundError:
		# For CLI usage, usually re-raising specific exceptions is better.
		raise

	except ValidationError as e:
		print(f'[ERROR] Invalid configuration in .ambyte/config.yaml:\n{e}')
		sys.exit(1)
	except yaml.YAMLError as e:
		print(f'[ERROR] Failed to parse YAML in .ambyte/config.yaml:\n{e}')
		sys.exit(1)


def save_config(config: AmbyteConfig, root_path: Path):
	"""
	Writes the AmbyteConfig object to disk as YAML.
	"""
	config_dir = root_path / CONFIG_DIR_NAME
	config_dir.mkdir(parents=True, exist_ok=True)

	config_path = config_dir / CONFIG_FILE_NAME

	# Pydantic -> Dict -> YAML
	# We use mode='json' to handle Path objects and Enums cleanly
	data = config.model_dump(mode='json', exclude_none=True)

	with open(config_path, 'w', encoding='utf-8') as f:
		yaml.dump(data, f, sort_keys=False, default_flow_style=False)

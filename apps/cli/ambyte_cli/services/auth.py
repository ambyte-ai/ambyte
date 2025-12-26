"""
Manages global user credentials stored in ~/.ambyte/credentials.
Handles security (file permissions) and precedence (Env Vars > File).
"""

import os
import stat
from pathlib import Path

import yaml
from ambyte_cli.config import get_workspace_root
from ambyte_cli.ui.console import console
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

# Global Constants
AMBYTE_HOME = Path.home() / '.ambyte'
CREDENTIALS_FILE = AMBYTE_HOME / 'credentials'


class UserCredentials(BaseModel):
	"""
	Schema for the global credentials file.
	Supports multiple profiles (e.g. [default], [prod]).
	"""

	api_key: str = Field(..., description='The sk_live_... machine key.')
	project_id: str | None = Field(None, description='The default project UUID.')
	organization_id: str | None = Field(None, description='The owner Org UUID.')


class CredentialsManager:
	"""
	Service to handle persistent authentication state for the CLI.
	"""

	def __init__(self, profile: str = 'default'):
		self.profile = profile
		self._bootstrap_env()

	def _bootstrap_env(self):
		"""
		Attempts to load .env files from the current directory or workspace root.
		"""
		# 1. Try CWD first
		cwd_env = Path.cwd() / '.env'
		if cwd_env.exists():
			load_dotenv(dotenv_path=str(cwd_env.absolute()))

		# 2. Try Workspace Root (where .ambyte/ lives)
		try:
			# get_workspace_root() is imported from ambyte_cli.config
			root = get_workspace_root()
			root_env = root / '.env'
			if root_env.exists() and root_env != cwd_env:
				load_dotenv(dotenv_path=str(root_env.absolute()))
		except (FileNotFoundError, Exception):  # noqa: S110
			# If not in a workspace yet, the CWD check above is our best bet
			pass

	def get_api_key(self) -> str | None:
		"""
		Retrieves the API Key using standard precedence:
		1. Environment Variable (Real shell env or loaded from .env)
		2. Local Credentials File (~/.ambyte/credentials)
		"""
		# load_dotenv was called in __init__, so os.getenv handles both
		env_key = os.getenv('AMBYTE_API_KEY')
		if env_key:
			return env_key

		# 2. Check Global File
		creds = self.load()
		if creds:
			return creds.api_key

		return None

	def load(self) -> UserCredentials | None:
		"""
		Reads the credentials file from the user's home directory.
		Returns None if the file doesn't exist or the profile is missing.
		"""
		if not CREDENTIALS_FILE.exists():
			return None

		try:
			with open(CREDENTIALS_FILE, encoding='utf-8') as f:
				data = yaml.safe_load(f) or {}

			profile_data = data.get(self.profile)
			if not profile_data:
				return None

			return UserCredentials.model_validate(profile_data)

		except (yaml.YAMLError, ValidationError) as e:
			console.print(f'[warning]Failed to parse credentials file: {e}[/warning]')
			return None

	def save(self, api_key: str, project_id: str | None = None, org_id: str | None = None):
		"""
		Persists credentials to disk and secures the file.
		"""
		# Ensure directory exists
		AMBYTE_HOME.mkdir(parents=True, exist_ok=True)

		# Load existing to avoid wiping other profiles
		existing_data = {}
		if CREDENTIALS_FILE.exists():
			with open(CREDENTIALS_FILE, encoding='utf-8') as f:
				existing_data = yaml.safe_load(f) or {}

		# Update specific profile
		new_creds = UserCredentials(api_key=api_key, project_id=project_id, organization_id=org_id)
		existing_data[self.profile] = new_creds.model_dump(exclude_none=True)

		# Write file
		with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
			yaml.dump(existing_data, f, sort_keys=False)

		# Secure the file (chmod 600: Read/Write for owner only)
		try:
			os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
		except OSError:
			# Fallback for systems where chmod isn't supported as expected
			pass

	def delete(self):
		"""
		Removes credentials for the current profile (Logout).
		"""
		if not CREDENTIALS_FILE.exists():
			return

		with open(CREDENTIALS_FILE, encoding='utf-8') as f:
			data = yaml.safe_load(f) or {}

		if self.profile in data:
			del data[self.profile]

			with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
				yaml.dump(data, f)

			console.print(f"[info]Logged out of profile '{self.profile}'.[/info]")

	@property
	def is_authenticated(self) -> bool:
		"""Helper to check if a valid key is available."""
		return self.get_api_key() is not None

import logging
import subprocess

import yaml
from ambyte_cli.config import AmbyteConfig
from ambyte_cli.services.loader import ObligationLoader
from ambyte_schemas.models.obligation import Obligation

logger = logging.getLogger(__name__)


class GitHistoryLoader:
	"""
	Loads obligations from a specific Git revision (e.g., HEAD~1, main).
	"""

	def __init__(self, config: AmbyteConfig):
		self.config = config
		self.loader_logic = ObligationLoader(config)  # Reuse parsing logic
		self.policies_path = config.policies_dir  # Relative path, e.g. "policies"

	def load_at_revision(self, revision: str) -> list[Obligation]:
		"""
		Traverses the policies directory structure at the given revision,
		reads file contents, and parses them.
		"""
		try:
			# 1. Verify revision exists
			self._run_git(['rev-parse', '--verify', revision])
		except subprocess.CalledProcessError as e:
			raise ValueError(f"Git revision '{revision}' not found.") from e

		# 2. List files in the policies directory at that revision
		# git ls-tree -r --name-only revision:policies/
		try:
			# We use the relative path for git command
			target_path = f'{revision}:{self.policies_path}'
			result = self._run_git(['ls-tree', '-r', '--name-only', target_path])
		except subprocess.CalledProcessError:
			# Likely the directory didn't exist in that revision
			return []

		file_paths = result.splitlines()
		obligations = []

		# 3. Read content of each file
		for file_path in file_paths:
			# file_path returned by ls-tree is relative to the root of the tree object passed
			# which means if we asked for 'HEAD:policies', we get 'gdpr.yaml'
			# To show it, we need 'HEAD:policies/gdpr.yaml'

			# NOTE: ls-tree behavior depends on how it's called.
			# If we call `git ls-tree -r HEAD policies/`, we get full paths like `policies/gdpr.yaml`
			# Let's use that approach for safety.

			if not (file_path.endswith('.yaml') or file_path.endswith('.yml')):
				continue

			full_git_ref = f'{revision}:{file_path}'

			try:
				content = self._run_git(['show', full_git_ref])
				raw_data = yaml.safe_load(content)
				if raw_data:
					ob = self.loader_logic.parse_obligation_data(raw_data, source_name=full_git_ref)
					obligations.append(ob)
			except Exception:
				# Silently skip broken files in history to focus on diff
				logger.warning('Failed to load obligation from %s, skipping.', full_git_ref, exc_info=True)
				continue

		return obligations

	def _run_git(self, args: list[str]) -> str:
		"""Runs a git command in the workspace root."""
		# We assume the .ambyte folder is inside a git repo.
		# We traverse up to find .ambyte, but git might be higher up.
		# CWD should generally be okay if the user is running ambyte cli inside the repo.
		cmd = ['git'] + args
		result = subprocess.run(  # noqa: S603
			cmd,
			capture_output=True,
			text=True,
			check=True,
			cwd=self.config.abs_policies_dir.parent,  # Run from project root
		)
		return result.stdout.strip()

	def get_changed_files(self, revision: str) -> list[str]:
		"""Returns list of files changed in policies/ between revision and HEAD."""
		# git diff --name-only revision -- policies/
		try:
			out = self._run_git(['diff', '--name-only', revision, '--', str(self.config.policies_dir)])
			return out.splitlines()
		except subprocess.CalledProcessError:
			return []

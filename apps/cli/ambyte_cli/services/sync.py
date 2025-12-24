import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from ambyte_cli.config import AmbyteConfig
from ambyte_cli.services.loader import ObligationLoader
from ambyte_schemas.models.obligation import Obligation as ObligationSchema

logger = logging.getLogger(__name__)


@dataclass
class SyncAction:
	slug: str
	status: str  # "NEW", "UPDATED", "UNCHANGED", "DELETED"
	path: Path
	title: str = ''
	source: str = ''


@dataclass
class PullResult:
	actions: list[SyncAction] = field(default_factory=list)
	project_name: str = ''


class SyncService:
	"""
	Handles synchronization between the Ambyte Control Plane and local YAML files.
	"""

	def __init__(self, config: AmbyteConfig, api_client: Any):
		self.config = config
		self.api_client = api_client
		self.loader = ObligationLoader(config)

	def pull(self, force: bool = False, prune: bool = False, dry_run: bool = False) -> PullResult:
		"""
		Synchronizes remote obligations to the local policies directory.
		"""
		result = PullResult(project_name=self.config.project_name)

		# 1. Fetch Remote State
		remote_obs = self._fetch_remote_obligations()
		remote_map = {ob.id: ob for ob in remote_obs}

		# 2. Map Local State (Slug -> Path)
		# We need to know WHERE the files are so we can overwrite them in place
		local_paths = self._get_local_file_map()

		# 3. Reconcile
		processed_slugs = set()

		for slug, remote_ob in remote_map.items():
			processed_slugs.add(slug)

			if slug in local_paths:
				# Check for updates
				local_path = local_paths[slug]
				is_changed = self._check_if_changed(local_path, remote_ob)

				if is_changed or force:
					status = 'UPDATED'
					if not dry_run:
						self._write_to_yaml(local_path, remote_ob)
				else:
					status = 'UNCHANGED'

				result.actions.append(
					SyncAction(
						slug=slug,
						status=status,
						path=local_path,
						title=remote_ob.title,
						source=remote_ob.provenance.source_id,
					)
				)
			else:
				# New Policy
				new_path = self.config.abs_policies_dir / f'{slug}.yaml'
				if not dry_run:
					self._write_to_yaml(new_path, remote_ob)

				result.actions.append(
					SyncAction(
						slug=slug,
						status='NEW',
						path=new_path,
						title=remote_ob.title,
						source=remote_ob.provenance.source_id,
					)
				)

		# 4. Handle Deletions (Pruning)
		if prune:
			for slug, path in local_paths.items():
				if slug not in processed_slugs:
					if not dry_run:
						path.unlink()
					result.actions.append(SyncAction(slug=slug, status='DELETED', path=path))

		return result

	def _fetch_remote_obligations(self) -> list[ObligationSchema]:
		"""
		Calls the SDK Client to get the current project obligations.
		"""
		# Ensure project_id is set (required for the API to context-switch)
		if not self.config.cloud.project_id:
			raise ValueError("Project ID missing in config. Run 'ambyte login' first.")

		# Use the new SDK method
		# The SDK handles the base_url, authentication, and retry logic
		try:
			data = self.api_client.list_obligations()
			return [ObligationSchema(**item) for item in data]
		except Exception as e:
			logger.error(f'Failed to fetch obligations from cloud: {e}')
			raise

	def _get_local_file_map(self) -> dict[str, Path]:
		"""
		Scans the policies directory and builds a map of Slug -> Path.
		This allows us to maintain the user's folder structure if they use subdirs.
		"""
		file_map = {}
		policy_dir = self.config.abs_policies_dir

		if not policy_dir.exists():
			return {}

		# Find all yaml/yml files
		paths = list(policy_dir.glob('**/*.yaml')) + list(policy_dir.glob('**/*.yml'))

		for p in paths:
			try:
				# Use existing loader logic to extract the 'id' (slug) from the file
				ob = self.loader._load_file(p)
				file_map[ob.id] = p
			except Exception as e:
				logger.warning(f'Skipping unparseable local policy {p.name}: {e}')

		return file_map

	def _check_if_changed(self, local_path: Path, remote_ob: ObligationSchema) -> bool:
		"""
		Semantic comparison to avoid unnecessary writes/git churn.
		"""
		try:
			local_ob = self.loader._load_file(local_path)
			# Compare model dumps to ignore formatting differences
			# We exclude system timestamps from comparison
			exclude = {'created_at', 'updated_at'}
			return local_ob.model_dump(exclude=exclude) != remote_ob.model_dump(exclude=exclude)
		except Exception:
			return True  # Assume changed if local is corrupt

	def _write_to_yaml(self, path: Path, ob: ObligationSchema):
		"""
		Serializes the Obligation model back to a clean, human-readable YAML file.
		"""
		path.parent.mkdir(parents=True, exist_ok=True)

		# Convert to dict, excluding None/unset values to keep YAML tidy
		data = ob.model_dump(mode='json', exclude_none=True, exclude={'created_at', 'updated_at'})

		# Custom YAML configuration for "Code-like" output
		class AmbyteDumper(yaml.SafeDumper):
			pass

		# Ensure blocks are used for multiline strings (like description)
		def str_presenter(dumper, data):
			if len(data.splitlines()) > 1:
				return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
			return dumper.represent_scalar('tag:yaml.org,2002:str', data)

		AmbyteDumper.add_representer(str, str_presenter)

		with open(path, 'w', encoding='utf-8') as f:
			f.write('# Ambyte Obligation (Synced from Cloud)\n')
			yaml.dump(data, f, Dumper=AmbyteDumper, sort_keys=False, default_flow_style=False, indent=2)

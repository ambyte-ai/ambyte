import logging
from pathlib import Path

import yaml

DEFAULT_MAPPING_PATH = Path('schemas/ontology/databricks_mappings.yaml')

logger = logging.getLogger('ambyte.connector.databricks.groups')


class GroupMapper:
	"""
	Translates abstract Ambyte Purposes (e.g., 'MARKETING') into concrete
	Databricks Account Groups (e.g., 'marketing-analysts').

	This ensures that policies defined in YAML ("Allowed Purpose: Marketing")
	can be compiled into valid Unity Catalog SQL ("is_account_group_member('marketing-analysts')").
	"""

	def __init__(self, mapping_file: Path | None = None):
		self.mapping_file = mapping_file or DEFAULT_MAPPING_PATH
		self._cache: dict[str, set[str]] = {}
		self._defaults: set[str] = set()
		self._loaded = False

	def load(self):
		"""Parses the YAML file into memory."""
		if self._loaded:
			return

		if not self.mapping_file.exists():
			logger.warning(
				f'Group mapping file not found at {self.mapping_file}. Purpose-to-Group translation will be empty.'
			)
			return

		try:
			with open(self.mapping_file, encoding='utf-8') as f:
				data = yaml.safe_load(f) or {}

			# Load Purpose Mappings
			mappings = data.get('mappings', [])
			for m in mappings:
				purpose = str(m.get('purpose', '')).upper().strip()
				groups = m.get('associated_groups', [])

				if purpose:
					if purpose not in self._cache:
						self._cache[purpose] = set()
					self._cache[purpose].update(groups)

			# Load Admin Defaults (Safety Valve)
			self._defaults = set(data.get('default_admin_groups', []))

			logger.info(f'Loaded mappings for {len(self._cache)} purposes from {self.mapping_file.name}')
			self._loaded = True

		except Exception as e:
			logger.error(f'Failed to parse group mappings: {e}')
			# Do not crash; treat as empty config to allow partial operation

	def resolve_groups(self, purposes: list[str]) -> list[str]:
		"""
		Returns a deduplicated list of Databricks Groups for the given purposes.
		Includes default admin groups automatically.
		"""
		if not self._loaded:
			self.load()

		resolved = set(self._defaults)  # Start with admins

		for p in purposes:
			# Normalize lookup key
			key = str(p).upper().strip()
			if key in self._cache:
				resolved.update(self._cache[key])
			else:
				logger.debug(f"No group mapping found for purpose '{key}'")

		return sorted(resolved)

	@property
	def admin_groups(self) -> list[str]:
		if not self._loaded:
			self.load()
		return sorted(self._defaults)

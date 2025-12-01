import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class RoleMapper:
	"""
	Translates abstract Ambyte Purposes into concrete Platform Roles.
	"""

	def __init__(self, mapping_file: Path):
		self.mapping_file = mapping_file
		self._cache: dict[str, set[str]] = {}
		self._defaults: set[str] = set()
		self._load()

	def _load(self):
		if not self.mapping_file.exists():
			logger.warning(
				'Role mapping file not found at %s. Purpose-to-Role translation will be empty.', self.mapping_file
			)
			return

		try:
			with open(self.mapping_file, encoding='utf-8') as f:
				data = yaml.safe_load(f) or {}

			# Load Mappings
			mappings = data.get('mappings', [])
			for m in mappings:
				purpose = m.get('purpose', '').upper()
				roles = m.get('associated_roles', [])
				if purpose:
					if purpose not in self._cache:
						self._cache[purpose] = set()
					self._cache[purpose].update(r.upper() for r in roles)

			# Load Admin Defaults (Safety Valve)
			self._defaults = {r.upper() for r in data.get('default_admin_roles', [])}

		except Exception as e:
			logger.error('Failed to parse role mappings: %s', e)

	def get_roles_for_purpose(self, purpose: str) -> list[str]:
		"""
		Returns a list of roles associated with a specific purpose.
		"""
		return list(self._cache.get(purpose.upper(), []))

	def get_roles_for_purposes(self, purposes: list[str]) -> list[str]:
		"""
		Aggregates roles for a list of purposes (e.g. denied_purposes).
		"""
		result = set()
		for p in purposes:
			result.update(self._cache.get(p.upper(), []))

		return sorted(result)

	def is_admin_role(self, role: str) -> bool:
		return role.upper() in self._defaults

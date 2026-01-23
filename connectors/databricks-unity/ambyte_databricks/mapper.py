import logging
from urllib.parse import urlparse

from ambyte_schemas.models.inventory import ResourceCreate

from ambyte_databricks.config import settings
from ambyte_databricks.crawler import DiscoveredAsset

logger = logging.getLogger('ambyte.connector.databricks.mapper')


class ResourceMapper:
	"""
	Transforms Databricks assets into Ambyte canonical Resources.
	"""

	def __init__(self):
		# Cache the cleaned workspace ID for URN generation
		self._workspace_id = self._extract_workspace_id(settings.HOST)

	def map(self, asset: DiscoveredAsset) -> ResourceCreate:
		"""
		Converts a raw DiscoveredAsset into a ResourceCreate payload.
		"""
		table = asset.table_info

		# 1. Generate URN
		# Format: urn:databricks:<workspace_id>:<catalog>.<schema>.<table>
		# We use lower() to ensure case-insensitive stability, though UC is case-preserving.
		urn = f'urn:databricks:{self._workspace_id}:{table.full_name}'.lower()

		# 2. Extract Columns
		# We need these to generate masking policies later (input types must match).
		columns_meta = []
		if table.columns:
			for col in table.columns:
				col_meta: dict[str, str | None | dict[str, str]] = {
					'name': col.name,
					'type': col.type_text,  # e.g. "STRING", "INT", "ARRAY<STRING>"
					'comment': col.comment,
				}
				# Include column-level tags if available
				if col.name and col.name in asset.column_tags:
					col_meta['tags'] = asset.column_tags[col.name]
				columns_meta.append(col_meta)

		# 3. Build Attributes
		# This generic JSONB dict holds all platform-specific metadata
		attributes = {
			'owner': table.owner,
			'table_type': table.table_type.name if table.table_type else 'UNKNOWN',
			'storage_location': table.storage_location,
			'created_at': table.created_at,
			'updated_at': table.updated_at,
			'columns': columns_meta,
			'tags': asset.tags,  # UC Tags map directly to Ambyte tags
			# Helper for policy targeting:
			# Allows users to target policies via 'catalog: "prod"' in YAML
			'hierarchy': {'catalog': table.catalog_name, 'schema': table.schema_name},
		}

		return ResourceCreate(urn=urn, platform='databricks', name=table.name, attributes=attributes)

	def _extract_workspace_id(self, host_url: str) -> str:
		"""
		Parses the Databricks Host URL to get a stable identifier.
		e.g. "https://adb-12345.1.azuredatabricks.net/" -> "adb-12345.1"
		e.g. "https://my-workspace.cloud.databricks.com" -> "my-workspace"
		"""
		try:
			parsed = urlparse(host_url)
			netloc = parsed.netloc or host_url  # Handle cases without scheme

			# Remove port if present
			hostname = netloc.split(':')[0]

			# Split domain parts
			parts = hostname.split('.')

			# Heuristic: The first part is usually the unique workspace ID
			return parts[0]
		except Exception:
			# Fallback to full string if parsing fails
			return 'unknown-workspace'

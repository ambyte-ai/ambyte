import logging
from dataclasses import dataclass, field
from typing import Generator

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import DatabricksError
from databricks.sdk.service.catalog import TableInfo, TableType

from .config import settings

logger = logging.getLogger('ambyte.connector.databricks.crawler')


@dataclass
class DiscoveredAsset:
	"""
	Intermediate container for a scanned Databricks asset.
	Bundles the core table metadata with separately fetched tags.
	"""

	table_info: TableInfo
	tags: dict[str, str] = field(default_factory=dict)


class UnityCatalogCrawler:
	"""
	Traverses the Unity Catalog hierarchy to discover tables and views.
	Respects inclusion/exclusion filters defined in settings.
	"""

	def __init__(self, client: WorkspaceClient):
		self.client = client

	def crawl(self) -> Generator[DiscoveredAsset, None, None]:
		"""
		Main entry point. Yields discovered assets lazily.
		"""
		logger.info('Starting Unity Catalog Crawl...')

		# 1. List Catalogs
		try:
			catalogs = self.client.catalogs.list()
		except DatabricksError as e:
			logger.critical(f'Failed to list catalogs: {e}')
			return

		for catalog in catalogs:
			if catalog.name is None or not self._should_scan_catalog(catalog.name):
				logger.debug(f'Skipping catalog: {catalog.name}')
				continue

			logger.info(f'Scanning Catalog: {catalog.name}')

			# 2. List Schemas (Databases) within Catalog
			try:
				schemas = self.client.schemas.list(catalog.name)
			except DatabricksError as e:
				logger.warning(f'Could not list schemas in {catalog.name}: {e}')
				continue

			for schema in schemas:
				if schema.name is None or not self._should_scan_schema(schema.name):
					continue

				# 3. List Tables/Views within Schema
				try:
					tables = self.client.tables.list(catalog.name, schema.name)
				except DatabricksError as e:
					logger.warning(f'Could not list tables in {catalog.name}.{schema.name}: {e}')
					continue

				for table in tables:
					# Enrich with Tags (Requires separate API call)
					# Note: This is an N+1 operation. In high-scale envs, this might be slow.
					# We catch errors here so one missing permission doesn't stop the crawl.
					tags = {}
					try:
						# Only attempt tag fetch for Managed/External tables or Views
						# Avoid temp views or weird system types if necessary
						if table.full_name and table.table_type in [
							TableType.MANAGED,
							TableType.EXTERNAL,
							TableType.VIEW,
						]:
							tag_assignments = self.client.entity_tag_assignments.list(
								entity_type='tables', entity_name=table.full_name
							)
							tags = {
								t.tag_key: t.tag_value for t in tag_assignments if t.tag_key and t.tag_value is not None
							}
					except DatabricksError:
						# Tags might fail on some view types or permissions
						pass

					yield DiscoveredAsset(table_info=table, tags=tags)

	def _should_scan_catalog(self, name: str) -> bool:
		"""
		Determines if a catalog is in scope based on Settings.
		"""
		# 1. Check Exclusions first
		if name in settings.EXCLUDE_CATALOGS:
			return False

		# 2. Check Inclusions
		# If "*" is present, allow everything not excluded
		if '*' in settings.INCLUDE_CATALOGS:
			return True

		# 3. Exact match
		return name in settings.INCLUDE_CATALOGS

	def _should_scan_schema(self, name: str) -> bool:
		"""
		Determines if a schema is in scope.
		Usually we skip 'information_schema' unless explicitly requested.
		"""
		if name == 'information_schema':
			return False

		# Simple wildcard support for now # TODO
		if '*' in settings.INCLUDE_SCHEMAS:
			return True

		return name in settings.INCLUDE_SCHEMAS

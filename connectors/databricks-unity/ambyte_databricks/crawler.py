import fnmatch
import logging
from collections.abc import Generator
from dataclasses import dataclass, field

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import DatabricksError
from databricks.sdk.service.catalog import TableInfo, TableType

from ambyte_databricks.config import settings

logger = logging.getLogger('ambyte.connector.databricks.crawler')


@dataclass
class DiscoveredAsset:
	"""
	Intermediate container for a scanned Databricks asset.
	Bundles the core table metadata with separately fetched tags.
	"""

	table_info: TableInfo
	tags: dict[str, str] = field(default_factory=dict)  # Table-level tags
	column_tags: dict[str, dict[str, str]] = field(default_factory=dict)  # Column name -> {tag_key: tag_value}


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
					# Enrich with Tags (Requires separate API calls)
					# Note: This is an N+1 operation. In high-scale envs, this might be slow.
					# We catch errors here so one missing permission doesn't stop the crawl.
					table_tags: dict[str, str] = {}
					column_tags: dict[str, dict[str, str]] = {}

					try:
						# Only attempt tag fetch for Managed/External tables or Views
						# Avoid temp views or weird system types if necessary
						if table.full_name and table.table_type in [
							TableType.MANAGED,
							TableType.EXTERNAL,
							TableType.VIEW,
						]:
							# 1. Fetch table-level tags
							tag_assignments = self.client.entity_tag_assignments.list(
								entity_type='tables', entity_name=table.full_name
							)
							table_tags = {
								t.tag_key: t.tag_value for t in tag_assignments if t.tag_key and t.tag_value is not None
							}

							# 2. Fetch column-level tags
							if table.columns:
								for col in table.columns:
									if not col.name:
										continue
									try:
										# Entity name for columns: catalog.schema.table.column
										col_full_name = f'{table.full_name}.{col.name}'
										col_tag_assignments = self.client.entity_tag_assignments.list(
											entity_type='columns', entity_name=col_full_name
										)
										col_tags = {
											t.tag_key: t.tag_value
											for t in col_tag_assignments
											if t.tag_key and t.tag_value is not None
										}
										if col_tags:
											column_tags[col.name] = col_tags
									except DatabricksError:
										# Individual column tag fetch might fail
										pass

					except DatabricksError:
						# Tags might fail on some view types or permissions
						pass

					yield DiscoveredAsset(table_info=table, tags=table_tags, column_tags=column_tags)

	def _should_scan_catalog(self, name: str) -> bool:
		"""
		Determines if a catalog is in scope based on Settings.
		Supports glob patterns (e.g., 'prod_*', '*_analytics').
		"""
		# 1. Check Exclusions first (supports glob patterns)
		if self._matches_any_pattern(name, settings.EXCLUDE_CATALOGS):
			return False

		# 2. Check Inclusions (supports glob patterns)
		return self._matches_any_pattern(name, settings.INCLUDE_CATALOGS)

	def _should_scan_schema(self, name: str) -> bool:
		"""
		Determines if a schema is in scope.
		Supports glob patterns (e.g., 'prod_*', '*_staging', 'data_*_v2').
		"""
		# 1. Check Exclusions first (supports glob patterns)
		if self._matches_any_pattern(name, settings.EXCLUDE_SCHEMAS):
			return False

		# 2. Check Inclusions (supports glob patterns)
		return self._matches_any_pattern(name, settings.INCLUDE_SCHEMAS)

	def _matches_any_pattern(self, name: str, patterns: list[str]) -> bool:
		"""
		Checks if the given name matches any of the glob patterns.

		Supports:
		- Exact match: 'sales'
		- Wildcard all: '*'
		- Prefix match: 'prod_*'
		- Suffix match: '*_staging'
		- Complex patterns: 'data_*_v2'
		"""
		for pattern in patterns:
			if fnmatch.fnmatch(name, pattern):
				return True
		return False

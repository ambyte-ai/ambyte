from pathlib import Path

import yaml
from ambyte_schemas.models.common import AmbyteBaseModel
from pydantic import Field, ValidationError
from rich.console import Console

console = Console()


class ResourceItem(AmbyteBaseModel):
	"""
	Represents a single entry in the resources.yaml inventory.
	"""

	urn: str = Field(..., description='The Unique Resource Name.')
	tags: dict[str, str] = Field(default_factory=dict, description='Metadata tags used for policy targeting.')
	description: str | None = None


class ResourceInventory(AmbyteBaseModel):
	"""
	The root schema for resources.yaml.
	"""

	resources: list[ResourceItem] = Field(default_factory=list)


class InventoryLoader:
	"""
	Responsible for loading the physical resource inventory from disk.
	"""

	def __init__(self, root_dir: Path):
		self.inventory_path = root_dir / 'resources.yaml'

	def load(self) -> list[ResourceItem]:
		"""
		Parses resources.yaml.
		If file is missing, returns a default wildcard resource for local dev.
		"""
		if not self.inventory_path.exists():
			console.print(f'[dim]No inventory found at {self.inventory_path}. Using default wildcard context.[/dim]')
			# Default for "Getting Started" - assumes one global resource
			return [ResourceItem(urn='urn:local:default', tags={}, description='Auto-generated default context')]

		try:
			with open(self.inventory_path, encoding='utf-8') as f:
				data = yaml.safe_load(f) or {}

			# Handle case where file is empty
			if not data:
				return []

			inventory = ResourceInventory.model_validate(data)
			return inventory.resources

		except ValidationError as e:
			console.print(f'[bold red]Invalid resources.yaml:[/bold red] {e}')
			raise
		except yaml.YAMLError as e:
			console.print(f'[bold red]Error parsing YAML in resources.yaml:[/bold red] {e}')
			raise

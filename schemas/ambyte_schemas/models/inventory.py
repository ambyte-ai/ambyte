from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResourceCreate(BaseModel):
	"""
	Input payload for registering a data asset.
	Used by Connectors to sync discovered assets to the platform.
	"""

	urn: str = Field(..., description="The Global Unique Identifier (e.g. 'urn:snowflake:prod:sales:customers').")
	platform: str = Field(..., description="The hosting platform (e.g., 'snowflake', 'aws-s3', 'databricks').")
	name: str | None = Field(default=None, description="Human-readable display name (e.g. 'Customer Churn Table').")
	attributes: dict[str, Any] = Field(
		default_factory=dict, description='Core metadata: tags, sensitivity, owner. Stored as JSONB.'
	)


class BatchResourceCreate(BaseModel):
	"""
	Wrapper for bulk inventory registration.
	Allows connectors to push 100s of tables in a single HTTP request.
	"""

	resources: list[ResourceCreate]


class ResourceResponse(ResourceCreate):
	"""
	Output model including system ID and timestamps.
	"""

	id: UUID
	project_id: UUID
	created_at: datetime
	updated_at: datetime

	model_config = ConfigDict(from_attributes=True)

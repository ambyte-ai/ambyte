from typing import Any

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, TimestampMixin, UUIDMixin


class Resource(Base, UUIDMixin, TimestampMixin, ProjectScopedMixin):
	"""
	Represents a data asset or model discovered by a Connector.
	Maps to 'ambyte_schemas.models.common.ResourceIdentifier' + metadata.
	"""

	__tablename__ = 'resources'

	# The Global Unique Identifier (e.g., "urn:snowflake:sales_db:customers")
	urn: Mapped[str] = mapped_column(String, index=True, nullable=False)

	# e.g., "snowflake", "aws-s3", "huggingface"
	platform: Mapped[str] = mapped_column(String, nullable=False)

	# Display name (e.g., "Customer Churn Table")
	name: Mapped[str] = mapped_column(String, nullable=True)

	# Core Metadata: Tags, Sensitivity Level, Owner Info
	# Pydantic Schema: { "tags": {"env": "prod"}, "sensitivity": "HIGH", "owner": "team-data" }
	attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

	# Ensure a URN is unique within a Project context
	__table_args__ = (UniqueConstraint('project_id', 'urn', name='uq_project_resource_urn'),)

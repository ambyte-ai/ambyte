from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, TimestampMixin, UUIDMixin


class Obligation(Base, UUIDMixin, TimestampMixin, ProjectScopedMixin):
	"""
	Represents a specific legal or contractual constraint.
	Example: "GDPR Article 17 - Right to Erasure".

	The 'definition' column stores the polymorphic JSON structure defined
	in ambyte-schemas (RetentionRule, GeoFencingRule, etc).
	"""

	__tablename__ = 'obligations'

	# Human-readable identifier (e.g., "gdpr-retention-customer-data")
	slug: Mapped[str] = mapped_column(String, index=True, nullable=False)

	title: Mapped[str] = mapped_column(String, nullable=False)

	# "BLOCKING", "AUDIT_ONLY", "NOTIFY_HUMAN"
	# Extracted from JSON for fast indexing/filtering
	enforcement_level: Mapped[str] = mapped_column(String, nullable=False, default='AUDIT_ONLY')

	# The full serialized ambyte_schemas.models.obligation.Obligation object
	definition: Mapped[dict] = mapped_column(JSONB, nullable=False)

	# Metadata for change management
	# e.g., Hash of the source document text to detect regulatory drifts
	source_hash: Mapped[str] = mapped_column(String, nullable=True)

	# Versioning
	version: Mapped[int] = mapped_column(default=1, nullable=False)
	is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

	# Optimization: Gin Index on the definition allows queries like:
	# SELECT * FROM obligations WHERE definition->'target'->'match_tags' @> '{"env": "prod"}'
	__table_args__ = (
		Index('ix_obligations_definition', definition, postgresql_using='gin'),
		UniqueConstraint('project_id', 'slug', name='uq_project_obligation_slug'),
	)

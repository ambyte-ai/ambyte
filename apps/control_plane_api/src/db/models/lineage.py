from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, UUIDMixin


class LineageRun(Base, UUIDMixin, ProjectScopedMixin):
	"""
	Represents a specific execution of a data process.
	Maps to 'ambyte_schemas.models.lineage.Run'.

	Examples: An Airflow DAG run, a SageMaker Training Job.
	"""

	__tablename__ = 'lineage_runs'

	# External ID from the orchestrator (e.g. "dag_run_id_2023-10-01")
	external_run_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

	run_type: Mapped[str] = mapped_column(String, nullable=False)  # "ETL", "TRAINING"

	started_at: Mapped[datetime] = mapped_column(nullable=False)
	ended_at: Mapped[datetime | None] = mapped_column(nullable=True)

	# Did the job actually succeed? (If failed, data might not have moved)
	success: Mapped[bool] = mapped_column(Boolean, default=False)

	# Actor who initiated this run
	triggered_by: Mapped[str | None] = mapped_column(String, nullable=True)

	# Relationships
	edges: Mapped[list['LineageEdge']] = relationship(back_populates='run', cascade='all, delete-orphan')


class LineageEdge(Base, UUIDMixin, ProjectScopedMixin):
	"""
	Represents a directional flow of data: Source -> Target.

	This is the core of the Dependency Graph.
	By querying this recursively, we answer: "What upstream data is in this Model?"
	"""

	__tablename__ = 'lineage_edges'

	run_id: Mapped[str] = mapped_column(ForeignKey('lineage_runs.id', ondelete='CASCADE'), nullable=False, index=True)

	# Source Resource URN
	source_urn: Mapped[str] = mapped_column(String, nullable=False, index=True)

	# Target Resource URN
	target_urn: Mapped[str] = mapped_column(String, nullable=False, index=True)

	# Relationship
	run: Mapped['LineageRun'] = relationship(back_populates='edges')

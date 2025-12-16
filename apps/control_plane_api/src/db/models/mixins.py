import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDMixin:
	"""
	Adds a standard UUID primary key.

	We use both a Python-side default (uuid.uuid4) and a Server-side default
	(gen_random_uuid) to ensure IDs are available immediately upon object creation
	in Python, while also supporting raw SQL inserts.
	"""

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True),
		primary_key=True,
		default=uuid.uuid4,
		server_default=func.gen_random_uuid(),
	)


class TimestampMixin:
	"""
	Adds created_at and updated_at columns.
	Uses database-side functions (func.now()) to ensure consistency across transactions.
	"""

	created_at: Mapped[datetime] = mapped_column(
		server_default=func.now(),
		nullable=False,
	)
	updated_at: Mapped[datetime] = mapped_column(
		server_default=func.now(),
		onupdate=func.now(),
		nullable=False,
	)


class ProjectScopedMixin:
	"""
	Mixin for resources that belong to a specific Project (Multi-tenancy).

	This enforces that every row must have a `project_id`.
	It assumes a table named 'projects' exists (defined in tenancy.py).
	"""

	@declared_attr
	def project_id(cls) -> Mapped[uuid.UUID]:
		return mapped_column(
			ForeignKey('projects.id', ondelete='CASCADE'),
			index=True,
			nullable=False,
		)

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base
from src.db.models.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
	from src.db.models.auth import User
	from src.db.models.tenancy import Project


class ProjectRole(StrEnum):
	"""
	Roles for project-level access control.
	Ordered from most to least privileged.
	"""

	OWNER = 'owner'  # Full control, can delete project, transfer ownership
	ADMIN = 'admin'  # Manage members, settings, but cannot delete project
	EDITOR = 'editor'  # Create/modify policies, resources, lineage
	VIEWER = 'viewer'  # Read-only access to project data


class ProjectMembership(Base, UUIDMixin, TimestampMixin):
	"""
	Links Users to Projects with a specific role.
	Enables project-level RBAC beyond organization membership.
	"""

	__tablename__ = 'project_memberships'

	# Composite unique constraint: one membership per user-project pair
	__table_args__ = (UniqueConstraint('user_id', 'project_id', name='uq_user_project'),)

	user_id: Mapped[str] = mapped_column(
		ForeignKey('users.id', ondelete='CASCADE'),
		nullable=False,
		index=True,
	)

	project_id: Mapped[str] = mapped_column(
		ForeignKey('projects.id', ondelete='CASCADE'),
		nullable=False,
		index=True,
	)

	role: Mapped[str] = mapped_column(
		String,
		nullable=False,
		default=ProjectRole.VIEWER,
	)

	# Relationships
	user: Mapped[User] = relationship(back_populates='project_memberships')
	project: Mapped[Project] = relationship(back_populates='members')

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base
from src.db.models.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
	from src.db.models.auth import ApiKey, User
	from src.db.models.membership import ProjectMembership


class Organization(Base, UUIDMixin, TimestampMixin):
	"""
	The top-level entity (Billing Unit).
	Example: "Acme Corp", "Startup Inc".
	"""

	__tablename__ = 'organizations'

	name: Mapped[str] = mapped_column(String, nullable=False, index=True)
	slug: Mapped[str] = mapped_column(String, unique=True, index=True)

	# Clerk Organization ID (for enterprise SSO sync)
	# Nullable because personal orgs created via self-serve don't have one
	external_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)

	# Billing / Plan info would go here in the future TODO
	# plan_tier: Mapped[str] = mapped_column(String, default="free")

	# Relationships
	projects: Mapped[list[Project]] = relationship(back_populates='organization', cascade='all, delete-orphan')
	users: Mapped[list[User]] = relationship(back_populates='organization', cascade='all, delete-orphan')


class Project(Base, UUIDMixin, TimestampMixin):
	"""
	An isolated workspace within an Organization.
	Example: "Production", "Staging", "Data Science Team".

	All policies, resources, and audit logs are scoped to a Project.
	"""

	__tablename__ = 'projects'

	name: Mapped[str] = mapped_column(String, nullable=False)

	# Optional: Human-readable ID like 'proj_prod_xyz' TODO
	# slug: Mapped[str] = mapped_column(String, index=True)

	organization_id: Mapped[str] = mapped_column(
		ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True
	)

	# Relationships
	organization: Mapped[Organization] = relationship(back_populates='projects')

	# We define reverse relationships as strings to avoid circular imports
	# if we haven't imported the other models yet.
	api_keys: Mapped[list[ApiKey]] = relationship(back_populates='project', cascade='all, delete-orphan')

	# User memberships (for project-level RBAC)
	members: Mapped[list[ProjectMembership]] = relationship(back_populates='project', cascade='all, delete-orphan')

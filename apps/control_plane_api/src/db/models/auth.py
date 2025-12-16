from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base
from src.db.models.mixins import ProjectScopedMixin, TimestampMixin, UUIDMixin
from src.db.models.tenancy import Organization, Project


class User(Base, UUIDMixin, TimestampMixin):
	"""
	A Human User who can log into the Admin Dashboard.
	If using Clerk/Auth0, this table is essentially a cache/profile extension.
	"""

	__tablename__ = 'users'

	email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
	full_name: Mapped[str | None] = mapped_column(String, nullable=True)

	# Store the external IDP ID (e.g. "auth0|12345")
	external_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)

	# Simple Role-Based Access Control (RBAC) for the Dashboard
	is_superuser: Mapped[bool] = mapped_column(default=False)

	# Link to Organization (Single-tenant view for now)
	organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

	organization: Mapped['Organization'] = relationship(back_populates='users')


class ApiKey(Base, UUIDMixin, TimestampMixin, ProjectScopedMixin):
	"""
	Machine Credentials for the SDK, CLI, and Airflow Operators.

	We NEVER store the raw key.
	- User sees: "sk_live_123abc..."
	- We store: SHA256("sk_live_123abc...")
	"""

	__tablename__ = 'api_keys'

	name: Mapped[str] = mapped_column(String, nullable=False)

	# The first few chars of the key (e.g. "sk_live_...") for UI identification
	prefix: Mapped[str] = mapped_column(String(10), nullable=False)

	# The secure hash of the full key
	key_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)

	# Optional expiration (good for rotation policies)
	expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

	# Scopes: ["read", "write", "check", "admin"]
	scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

	# Metadata for tracking usage
	last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)

	# Relationship to Project defined in Mixin
	project: Mapped['Project'] = relationship(back_populates='api_keys')

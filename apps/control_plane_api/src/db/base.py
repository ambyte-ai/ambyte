from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

# Define a rigid naming convention for database constraints.
# This ensures that Alembic can automatically detect and name indexes/keys correctly
# across different environments, preventing migration headaches.
POSTGRES_NAMING_CONVENTION = {
	'ix': 'ix_%(column_0_label)s',
	'uq': 'uq_%(table_name)s_%(column_0_name)s',
	'ck': 'ck_%(table_name)s_%(constraint_name)s',
	'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
	'pk': 'pk_%(table_name)s',
}


class Base(AsyncAttrs, DeclarativeBase):
	"""
	Base class for all SQLAlchemy ORM models.

	Inherits from:
	- AsyncAttrs: Adds .awaitable_attrs to models, allowing lazy loading in async contexts.
	- DeclarativeBase: The new SQLAlchemy 2.0 standard root class.
	"""

	metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)

	# Note: We do NOT auto-generate __tablename__ here.
	# In enterprise apps, explicit table names in the Model definitions
	# are safer to prevent accidental schema changes during refactors.

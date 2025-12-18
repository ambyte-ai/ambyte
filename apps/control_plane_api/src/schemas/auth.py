from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# Input: Create
class ApiKeyCreate(BaseModel):
	name: str = Field(..., description="Human-readable name (e.g. 'Production Airflow')")
	scopes: list[str] = Field(default=['check:write', 'audit:write'], description='Allowed actions')
	expires_at: datetime | None = None


# Output: Metadata (Safe to show)
class ApiKeyRead(BaseModel):
	id: UUID
	name: str
	prefix: str
	scopes: list[str]
	created_at: datetime
	last_used_at: datetime | None
	expires_at: datetime | None


# Output: Secret (Shown ONLY once upon creation)
class ApiKeySecret(BaseModel):
	key: str = Field(..., description='The raw secret key. Store this securely!')
	info: ApiKeyRead

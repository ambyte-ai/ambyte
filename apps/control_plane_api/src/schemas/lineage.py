from datetime import datetime

from ambyte_schemas.models.lineage import RunType
from pydantic import BaseModel, Field


class LineageRunCreate(BaseModel):
	"""
	Payload for creating or updating a Job Execution (Run).
	Sent twice by the SDK:
	1. At Start: contains `started_at` and `run_type`.
	2. At End: contains `ended_at` and `success` status.
	"""

	# The UUID generated client-side by the SDK (e.g. via uuid4())
	external_run_id: str = Field(..., description='Client-side unique identifier for the run execution.')

	# Metadata
	run_type: RunType = Field(default=RunType.UNSPECIFIED, description='Type of process (ETL, Training, etc.)')
	triggered_by: str | None = Field(default=None, description='Actor ID who initiated this run.')

	# Timestamps (Optional because start/end are separate events)
	started_at: datetime | None = None
	ended_at: datetime | None = None

	# Status
	success: bool = Field(default=False, description='Final status of the run.')


class LineageEventCreate(BaseModel):
	"""
	Payload for recording data movement (Edges).
	Links inputs (Sources) to outputs (Targets) via a specific Run.
	"""

	external_run_id: str = Field(..., description='Must match the ID of a previously created Run.')

	# We use lists of URN strings.
	# The Service layer will resolve these URNs to Resource IDs or create placeholders.
	inputs: list[str] = Field(default_factory=list, description='List of Source URNs read by this run.')
	outputs: list[str] = Field(default_factory=list, description='List of Destination URNs written by this run.')

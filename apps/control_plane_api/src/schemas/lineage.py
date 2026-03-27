from datetime import datetime

from ambyte_schemas.models.lineage import RunType
from pydantic import BaseModel, ConfigDict, Field


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


class GraphNode(BaseModel):
	"""
	Represents a Node (Resource or Model) in the React Flow Canvas.
	"""

	id: str = Field(..., description='The URN of the asset.')
	label: str = Field(..., description='Human readable name or fallback URN.')
	platform: str = Field(default='unknown', description='e.g., snowflake, databricks, huggingface')
	node_type: str = Field(default='resource', description="'resource' or 'model'")

	# Governance Metadata
	sensitivity: str = Field(default='UNSPECIFIED')
	risk_level: str = Field(default='UNSPECIFIED')
	tags: dict[str, str] = Field(default_factory=dict)

	# Indicate if this node has restrictions (the "Poison Pill" indicator)
	is_ai_restricted: bool = Field(default=False)

	model_config = ConfigDict(from_attributes=True)


class GraphEdge(BaseModel):
	"""
	Represents a directed Edge (Data Flow) in the React Flow Canvas.
	"""

	id: str = Field(..., description='Unique edge identifier.')
	source: str = Field(..., description='Source URN')
	target: str = Field(..., description='Target URN')

	# Execution Metadata
	run_id: str
	run_type: str
	success: bool
	actor_id: str | None = None
	start_time: datetime | None = None


class LineageGraphResponse(BaseModel):
	"""
	The complete topology payload for the frontend.
	"""

	nodes: list[GraphNode]
	edges: list[GraphEdge]


class LineageAnalysisResponse(BaseModel):
	"""
	Response model for the diagnostic lineage endpoint.
	Used by the frontend Inspector to display inherited constraints.
	"""

	target_urn: str = Field(..., description='The URN being analyzed.')
	inherited_risk: str = Field(..., description='The maximum risk severity inherited from ancestors.')
	inherited_sensitivity: str = Field(..., description='The maximum sensitivity inherited from ancestors.')

	# The "Poison Pills"
	poisoned_constraints: list[str] = Field(
		default_factory=list,
		description='List of upstream URNs that are explicitly blocking usage (e.g., ai_training_allowed=False).',
	)

	# The Topology Path
	upstream_path: list[str] = Field(
		default_factory=list, description='Flat list of all ancestor URNs flowing into the target.'
	)

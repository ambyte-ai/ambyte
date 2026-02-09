from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestStatus(StrEnum):
	"""
	Lifecycle state of an ingestion job.
	"""

	QUEUED = 'QUEUED'
	PARSING = 'PARSING'  # OCR / Text Extraction
	CHUNKING = 'CHUNKING'  # Semantic Splitting
	EMBEDDING = 'EMBEDDING'  # Vector Generation
	DEFINING = 'DEFINING'  # (Pass 1) Extracting Definitions
	EXTRACTION = 'EXTRACTION'  # (Pass 2) Extracting Rules
	MERGING = 'MERGING'  # (Pass 3) Deduplication
	SYNCING = 'SYNCING'  # Pushing to Control Plane
	COMPLETED = 'COMPLETED'
	FAILED = 'FAILED'


class IngestJobRead(BaseModel):
	"""
	Represents the state of a background document processing job.
	Data is sourced from shared Redis storage populated by the Ingest Worker.
	"""

	# Config to ensure Enums are serialized as strings for the frontend
	model_config = ConfigDict(use_enum_values=True)

	job_id: str = Field(..., description='Unique UUID for the ingestion task.')
	status: IngestStatus = Field(..., description='Current lifecycle stage.')
	message: str | None = Field(default=None, description='Human-readable progress or error message.')

	# Contains dynamic metadata like:
	# {
	#   "filename": "MSA.pdf",
	#   "duration_seconds": 12.5,
	#   "chunks_processed": 50,
	#   "final_obligations_count": 5
	# }
	stats: dict[str, Any] = Field(default_factory=dict, description='Execution metrics and file metadata.')

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IngestStatus(StrEnum):
	"""
	Lifecycle state of an ingestion job.
	"""

	QUEUED = 'QUEUED'
	PARSING = 'PARSING'  # OCR / Text Extraction
	CHUNKING = 'CHUNKING'  # Semantic Splitting
	EMBEDDING = 'EMBEDDING'  # Vector Generation
	EXTRACTION = 'EXTRACTION'  # LLM Processing
	COMPLETED = 'COMPLETED'
	FAILED = 'FAILED'


class DocumentMetadata(BaseModel):
	"""
	Contextual metadata about a specific chunk of text.
	Critical for the 'Provenance' feature in Ambyte (e.g. 'Page 5, Section 3.1').
	"""

	filename: str = Field(..., description='Original filename uploaded.')
	page_number: int = Field(..., description='The physical page number (1-indexed).')

	# Hierarchy tracking is vital for legal docs.
	# Example: ["Data Processing Agreement", "3. Security Measures", "3.1 Encryption"]
	section_hierarchy: list[str] = Field(
		default_factory=list, description='The path of headers leading to this text chunk.'
	)

	# "NarrativeText", "Table", "ListItem", "Title"
	element_type: str = Field(default='NarrativeText', description='The structural category determined by the parser.')

	# Store raw bbox if needed for UI highlighting later # TODO
	# bbox: list[float] | None = None


class DocumentChunk(BaseModel):
	"""
	The atomic unit of data passed to the Vector Store and LLM.
	"""

	chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)

	# The actual legal text
	content: str = Field(..., description='Cleaned text content.')

	# Metadata for filter/retrieval
	metadata: DocumentMetadata

	# Approximate token count (useful for context window management)
	token_count: int = Field(default=0)


class IngestRequest(BaseModel):
	"""
	Payload for initiating an ingestion job via API.
	"""

	# If provided, we associate the extracted obligations with this project context
	project_id: str | None = None

	# Optional hints to guide the extractor (e.g., "This is a DPA", "This is a MSA")
	document_type_hint: str | None = None


class IngestJobResponse(BaseModel):
	"""
	API Response for job tracking.
	"""

	job_id: str
	status: IngestStatus
	message: str | None = None

	# When complete, this will contain the count of extracted items
	stats: dict[str, Any] = Field(default_factory=dict)

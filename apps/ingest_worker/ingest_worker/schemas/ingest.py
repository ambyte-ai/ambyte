import uuid
from enum import StrEnum
from typing import Any

from ambyte_schemas.models.obligation import (
	AiModelConstraint,
	GeofencingRule,
	PrivacyEnhancementRule,
	PurposeRestriction,
	RetentionRule,
)
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


class DefinedTerm(BaseModel):
	"""
	A specific variable defined in the contract.
	e.g., "Customer Data", "Authorized Region".
	"""

	term: str = Field(..., description='The capitalized term being defined.')
	definition: str = Field(..., description='The verbatim definition text.')
	source_context: str | None = Field(None, description='Where this definition was found.')


class ContractContext(BaseModel):
	"""
	The global context extracted from the Definitions section.
	Injected into prompts during Pass 2 to resolve ambiguity.
	"""

	definitions: list[DefinedTerm] = Field(default_factory=list)
	effective_date: str | None = None
	parties: list[str] = Field(default_factory=list)


class ConstraintCategory(StrEnum):
	RETENTION = 'RETENTION'
	GEOFENCING = 'GEOFENCING'
	PURPOSE = 'PURPOSE'
	PRIVACY = 'PRIVACY'
	AI_MODEL = 'AI_MODEL'
	UNKNOWN = 'UNKNOWN'


class ExtractedConstraint(BaseModel):
	"""
	Intermediate representation used by the LLM (Instructor).

	We force the LLM to output this structure BEFORE converting to the strict
	'Obligation' schema. This allows us to validate the 'quote' (hallucination check)
	and capture the 'rationale' (Chain-of-Thought) before committing to DB.
	"""

	# 1. Classification
	category: ConstraintCategory = Field(..., description='The domain of this rule.')

	# 2. Provenance / Anti-Hallucination
	quote: str = Field(
		..., description='The EXACT substring from the text that justifies this rule. Do not paraphrase.'
	)
	rationale: str = Field(..., description='Explain why this text maps to the chosen technical rule.')

	# 3. Scoping (Targeting)
	subject: str = Field(
		..., description="The specific data category this applies to (e.g. 'Customer Data', 'Usage Logs')."
	)

	# 4. The Technical Payload (Polymorphic)
	# The LLM must populate EXACTLY ONE of these based on the category.
	# We use optional fields rather than Union to make it easier for smaller models to steer.
	retention_rule: RetentionRule | None = None
	geofencing_rule: GeofencingRule | None = None
	purpose_rule: PurposeRestriction | None = None
	privacy_rule: PrivacyEnhancementRule | None = None
	ai_rule: AiModelConstraint | None = None


class ExtractionResult(BaseModel):
	"""
	Container for the raw output of Pass 2 for a specific chunk.
	"""

	constraints: list[ExtractedConstraint] = Field(default_factory=list)


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
	Configured to allow seamless serialization/deserialization from Redis JSON.
	"""

	# Ensures the Enum (IngestStatus) is treated as a primitive string
	# when dumping to JSON/Redis, preventing object reconstruction issues.
	model_config = ConfigDict(use_enum_values=True)

	job_id: str
	status: IngestStatus
	message: str | None = None

	# When complete, this will contain the count of extracted items
	stats: dict[str, Any] = Field(default_factory=dict)

import logging

import instructor
from ingest_worker.config import settings
from ingest_worker.intelligence.prompts import (
	SYSTEM_PROMPT_CONSTRAINTS,
	SYSTEM_PROMPT_DEFINITIONS,
	format_constraint_user_prompt,
	format_definition_user_prompt,
)
from ingest_worker.schemas.ingest import ContractContext, ExtractionResult
from openai import AsyncOpenAI
from tenacity import (
	retry,
	retry_if_exception_type,
	stop_after_attempt,
	wait_exponential,
)

logger = logging.getLogger(__name__)


class LlmClient:
	"""
	The reasoning engine interface.
	Wraps OpenAI with 'instructor' to enforce strict Pydantic output schemas.
	"""

	def __init__(self):
		# We use Mode.TOOLS as it is currently the most robust for nested structures
		# like the polymorphic 'ExtractedConstraint'.
		self.client = instructor.from_openai(
			AsyncOpenAI(api_key=settings.openai_api_key_val),
			mode=instructor.Mode.TOOLS,
		)
		self.model = settings.EXTRACTION_MODEL

	@retry(
		retry=retry_if_exception_type(Exception),
		stop=stop_after_attempt(3),
		wait=wait_exponential(multiplier=1, min=2, max=30),
		reraise=True,
	)
	async def extract_definitions(self, text_chunk: str) -> ContractContext:
		"""
		PASS 1: Identify capitalized defined terms in the text.
		Returns a ContractContext object containing the dictionary of terms.
		"""
		logger.debug('LLM: Extracting definitions...')

		try:
			resp = await self.client.chat.completions.create(
				model=self.model,
				response_model=ContractContext,
				messages=[
					{'role': 'system', 'content': SYSTEM_PROMPT_DEFINITIONS},
					{'role': 'user', 'content': format_definition_user_prompt(text_chunk)},
				],
				temperature=0.0,  # Strict determinism for definitions
			)
			return resp

		except Exception as e:
			logger.error(f'Definition extraction failed: {e}')
			raise

	@retry(
		retry=retry_if_exception_type(Exception),
		stop=stop_after_attempt(3),
		wait=wait_exponential(multiplier=1, min=2, max=30),
		reraise=True,
	)
	async def extract_constraints(
		self, text_chunk: str, context: ContractContext | None = None, regulatory_context: str = ''
	) -> ExtractionResult:
		"""
		PASS 2: Extract technical obligations.
		Injects:
		1. Glossary (Definitions)
		2. Knowledge Graph (Canonical Regulations)
		"""
		logger.debug('LLM: Extracting constraints...')

		# Prepare context string (if any)
		definitions_str = ''
		if context and context.definitions:
			lines = [f'- {d.term}: {d.definition}' for d in context.definitions]
			definitions_str = '\n'.join(lines)

		try:
			resp = await self.client.chat.completions.create(
				model=self.model,
				response_model=ExtractionResult,
				messages=[
					{'role': 'system', 'content': SYSTEM_PROMPT_CONSTRAINTS},
					{
						'role': 'user',
						'content': format_constraint_user_prompt(text_chunk, definitions_str, regulatory_context),
					},
				],
				# Slight temperature allows for better reasoning on 'rationale' field
				temperature=0.1,
				# validation_context allows custom validators in schemas if we add them later
				validation_context={'text_chunk': text_chunk},
			)
			return resp

		except Exception as e:
			logger.error(f'Constraint extraction failed: {e}')
			raise

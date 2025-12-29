import logging

import tiktoken
from ingest_worker.schemas.ingest import DocumentChunk, DocumentMetadata
from unstructured.documents.elements import Element, Table, Title

logger = logging.getLogger(__name__)


class SectionChunker:
	"""
	Groups unstructured Elements into semantic DocumentChunks based on:
	1. Token limits (context window management).
	2. Section boundaries (Titles trigger new chunks).
	3. Structural isolation (Tables are kept separate).
	"""

	def __init__(self, max_tokens: int = 1000, model_encoding: str = 'cl100k_base'):
		"""
		Args:
		    max_tokens: The soft limit for a single chunk.
		    model_encoding: The tokenizer scheme.
		"""  # noqa: E101
		self.max_tokens = max_tokens
		self.tokenizer = tiktoken.get_encoding(model_encoding)

	def chunk(self, elements: list[Element], filename: str) -> list[DocumentChunk]:
		"""
		Main entry point to transform elements into chunks.
		"""
		chunks: list[DocumentChunk] = []

		# State tracking
		current_buffer: list[str] = []
		current_token_count = 0

		# Context tracking
		current_section_title = 'Preamble'  # Default context before first header
		# We track the page number of the *first* element in the buffer
		current_start_page = 1

		for el in elements:
			# ------------------------------------------------------------------
			# 1. Handle Titles (Context Switch)
			# ------------------------------------------------------------------
			if isinstance(el, Title):
				# If we have gathered text, flush it before switching context.
				# This prevents text from Section A appearing under Header B.
				if current_buffer:
					chunks.append(
						self._create_chunk(
							buffer=current_buffer,
							filename=filename,
							page=current_start_page,
							section=current_section_title,
							tokens=current_token_count,
						)
					)
					self._reset_buffer(current_buffer, current_token_count)

				# Update context
				current_section_title = el.text.strip()
				# Update page number for the *next* block
				current_start_page = self._get_page_number(el)

				# We do NOT add the Title text to the buffer yet;
				# it serves as metadata for the *following* text.
				continue

			# ------------------------------------------------------------------
			# 2. Handle Tables (Isolation)
			# ------------------------------------------------------------------
			if isinstance(el, Table):
				# Flush pending text first
				if current_buffer:
					chunks.append(
						self._create_chunk(
							buffer=current_buffer,
							filename=filename,
							page=current_start_page,
							section=current_section_title,
							tokens=current_token_count,
						)
					)
					self._reset_buffer(current_buffer, current_token_count)

				# Create a specialized chunk for the table
				# We prefer the HTML representation if available for LLM readability
				table_content = (
					el.metadata.text_as_html
					if hasattr(el.metadata, 'text_as_html') and el.metadata.text_as_html
					else el.text
				)

				chunks.append(
					DocumentChunk(
						content=table_content,
						token_count=self._count_tokens(table_content),
						metadata=DocumentMetadata(
							filename=filename,
							page_number=self._get_page_number(el),
							section_hierarchy=[current_section_title],
							element_type='Table',
						),
					)
				)
				continue

			# ------------------------------------------------------------------
			# 3. Handle Narrative Text / List Items
			# ------------------------------------------------------------------
			text = el.text.strip()
			if not text:
				continue

			# Check if this addition would overflow the token limit
			# (We estimate addition: existing + new text + 1 newline token)
			new_tokens = self._count_tokens(text)

			if current_token_count + new_tokens > self.max_tokens:
				# Flush current
				chunks.append(
					self._create_chunk(
						buffer=current_buffer,
						filename=filename,
						page=current_start_page,
						section=current_section_title,
						tokens=current_token_count,
					)
				)
				# Reset
				current_buffer = []
				current_token_count = 0
				current_start_page = self._get_page_number(el)

			# Add to buffer
			if not current_buffer:
				# If this is the first element, ensure we capture its page number
				current_start_page = self._get_page_number(el)

			current_buffer.append(text)
			current_token_count += new_tokens

		# ------------------------------------------------------------------
		# 4. Final Flush
		# ------------------------------------------------------------------
		if current_buffer:
			chunks.append(
				self._create_chunk(
					buffer=current_buffer,
					filename=filename,
					page=current_start_page,
					section=current_section_title,
					tokens=current_token_count,
				)
			)

		return chunks

	def _create_chunk(self, buffer: list[str], filename: str, page: int, section: str, tokens: int) -> DocumentChunk:
		"""Helper to construct the Pydantic object."""
		content = '\n\n'.join(buffer)

		# Double check token count on the final joined string (joins add tokens)
		final_tokens = self._count_tokens(content)

		return DocumentChunk(
			content=content,
			token_count=final_tokens,
			metadata=DocumentMetadata(
				filename=filename, page_number=page, section_hierarchy=[section], element_type='NarrativeText'
			),
		)

	def _reset_buffer(self, buffer: list, count: int):
		"""Simple helper to clear references (Python lists are mutable)."""
		buffer.clear()
		# count is immutable int, handled in caller

	def _count_tokens(self, text: str) -> int:
		return len(self.tokenizer.encode(text))

	def _get_page_number(self, element: Element) -> int:
		"""Safely extract page number from unstructured metadata."""
		if hasattr(element, 'metadata') and element.metadata.page_number:
			return element.metadata.page_number
		return 1

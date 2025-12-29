import logging
from typing import BinaryIO

from unstructured.cleaners.core import clean, clean_extra_whitespace, group_broken_paragraphs, replace_unicode_quotes
from unstructured.documents.elements import Element, ElementMetadata
from unstructured.partition.pdf import partition_pdf

from .base import BaseParser

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
	"""
	High-fidelity PDF extractor optimized for legal contracts.
	Uses layout analysis (OCR/Vision) to detect headers, footers, and tables.
	"""

	def parse(self, file: BinaryIO, filename: str | None = None) -> list[Element]:
		"""
		Parses a PDF file stream into a list of semantic elements.

		We use the 'hi_res' strategy because legal documents often rely on
		visual cues (bolding, indentation, tables) that standard text extraction misses.
		"""
		logger.info(f'Starting hi_res PDF partition for: {filename or "unknown"}')

		try:
			# 1. Partitioning
			elements = partition_pdf(
				file=file,
				file_filename=filename,
				strategy='hi_res',
				infer_table_structure=True,
				include_page_breaks=False,
			)

			# 2. Cleaning & Post-processing
			cleaned_elements = self._clean_elements(elements)

			logger.info(f'Successfully extracted {len(cleaned_elements)} elements from {filename}')
			return cleaned_elements

		except Exception as e:
			logger.error(f'Failed to parse PDF {filename}: {e}', exc_info=True)
			raise ValueError(f'PDF parsing failed: {str(e)}') from e

	def _clean_elements(self, elements: list[Element]) -> list[Element]:
		"""
		Applies text normalization rules to the raw elements.
		"""
		processed = []

		for el in elements:
			# Skip empty elements
			if not el.text or not el.text.strip():
				continue

			# Skip Header/Footer elements usually detected by 'hi_res' strategy
			# These often interrupt sentences across pages (e.g. "Confidential - Page 2")
			if el.category in ['Header', 'Footer']:
				continue

			# 1. Basic Cleaning (Quotes, non-ascii noise)
			txt = replace_unicode_quotes(el.text)

			# 2. Whitespace Normalization
			# "Lawful   Basis" -> "Lawful Basis"
			txt = clean_extra_whitespace(txt)

			# 3. Clean Bullets (optional, usually handled well by partition)
			txt = clean(txt, bullets=True, extra_whitespace=True, dashes=True)
			txt = group_broken_paragraphs(txt)

			# Update the element text in place
			el.text = txt

			# Ensure metadata is initialized if missing (safety check)
			if el.metadata is None:
				el.metadata = ElementMetadata()

			processed.append(el)

		return processed

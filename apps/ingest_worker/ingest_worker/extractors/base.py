from abc import ABC, abstractmethod
from typing import BinaryIO

from unstructured.documents.elements import Element


class BaseParser(ABC):
	"""
	Interface for document parsers that ingest raw files and output layout-aware Elements.
	"""

	@abstractmethod
	def parse(self, file: BinaryIO, filename: str | None = None) -> list[Element]:
		"""
		Process the raw file stream into a linear list of Elements (Titles, Text, Tables).

		Args:
		    file: The binary file stream (e.g. SpooledTemporaryFile from FastAPI).
		    filename: Optional name of the file (useful for debugging/logging).

		Returns:
		    A list of unstructured Elements. These preserve layout info (like 'category')
		    but are not yet semantically chunked.
		"""  # noqa: E101
		pass

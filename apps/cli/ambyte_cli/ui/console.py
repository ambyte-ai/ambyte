"""
Global Rich Console instance for consistent CLI output styling.
"""

from rich.console import Console
from rich.theme import Theme

# Define the Ambyte Brand Theme
# This allows us to use tags like [info], [good], [bad] in print statements
# instead of hardcoding colors everywhere.
_ambyte_theme = Theme(
	{
		'info': 'dim cyan',
		'warning': 'yellow',
		'error': 'bold red',
		'good': 'green',
		'bad': 'red',
		'neutral': 'blue',
		'highlight': 'bold magenta',
		'urn': 'underline cyan',
		'source': 'bold italic white',
	}
)

# Singleton instance
console = Console(theme=_ambyte_theme, legacy_windows=False)


def error_console() -> Console:
	"""Returns a console writing to stderr."""
	return Console(theme=_ambyte_theme, stderr=True, legacy_windows=False)

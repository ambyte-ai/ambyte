from pydantic import SecretStr

from ambyte.client import AmbyteClient
from ambyte.config import AmbyteMode
from ambyte.context import context
from ambyte.decorators import audit, guard
from ambyte.integrations.databricks import databricks_init
from ambyte.tracking.lineage import trace


def init(api_key: str | None = None, mode: str | None = None):
	"""
	Helper to initialize the SDK singleton.
	"""
	from ambyte.config import get_config

	cfg = get_config()
	if api_key:
		cfg.api_key = SecretStr(api_key)
	if mode:
		cfg.mode = AmbyteMode(mode)

	# Initialize connection
	AmbyteClient.get_instance()


__all__ = ['AmbyteClient', 'guard', 'audit', 'context', 'trace', 'init', 'databricks_init']

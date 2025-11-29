import logging
import uuid
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
	from ambyte_schemas.models.common import Actor, ActorType
else:
	try:
		from ambyte_schemas.models.common import Actor, ActorType
	except ImportError:
		# Fallback if schemas aren't installed during very early dev
		# In production, dependencies ensure this never happens
		Actor = Any
		ActorType = Any

# Optional OpenTelemetry integration
try:
	from opentelemetry import trace

	_OTEL_AVAILABLE = True
except ImportError:
	trace = None
	_OTEL_AVAILABLE = False

logger = logging.getLogger('ambyte.context')

# ==============================================================================
# Context Variables
# These store state local to the current Task/Thread request
# ==============================================================================

_current_actor: ContextVar[Optional[Actor]] = ContextVar('ambyte_actor', default=None)
_current_run_id: ContextVar[Optional[str]] = ContextVar('ambyte_run_id', default=None)
_extra_context: ContextVar[Optional[dict[str, Any]]] = ContextVar('ambyte_extras', default=None)

# ==============================================================================
# Getters
# ==============================================================================


def get_current_actor() -> Optional[Actor]:
	"""Returns the actor currently active in this context."""
	return _current_actor.get()


def get_current_run_id() -> Optional[str]:
	"""
	Returns the current Run ID.
	If none was explicitly set, one is NOT generated here to avoid side effects.
	It returns None or the value.
	(Wrapper logic often defaults to 'anonymous' if this returns None).
	"""
	return _current_run_id.get()


def get_extra_context() -> dict[str, Any]:
	"""Returns arbitrary dictionary context set by the user."""
	return _extra_context.get() or {}


# ==============================================================================
# OpenTelemetry Sync Helper
# ==============================================================================


def _sync_otel_span(actor: Optional[Actor], run_id: Optional[str]):
	"""
	If OpenTelemetry is installed and a Span is active, inject Ambyte metadata.
	This links 'Policy Checks' to 'Datadog Traces'.
	"""
	if not _OTEL_AVAILABLE:
		return

	assert trace is not None
	span = trace.get_current_span()
	if span == trace.INVALID_SPAN:
		return

	if run_id:
		span.set_attribute('ambyte.run_id', run_id)

	if actor:
		span.set_attribute('ambyte.actor.id', actor.id)
		# Store enum value as int or string depending on schema preference
		span.set_attribute('ambyte.actor.type', str(actor.type))
		if actor.roles:
			span.set_attribute('ambyte.actor.roles', actor.roles)


# ==============================================================================
# Context Manager
# ==============================================================================


class AmbyteContext:
	"""
	A Context Manager to define the scope of an Actor or Execution Run.
	Handles setting and resetting ContextVars automatically.

	Usage:
	    actor = Actor(id="user_123", type=ActorType.HUMAN)
	    with ambyte.context(actor=actor):
	        # All checks here are attributed to user_123
	        ambyte.guard(...)
	"""  # noqa: E101

	def __init__(
		self, actor: Optional[Actor] = None, run_id: Optional[str] = None, extras: Optional[dict[str, Any]] = None
	):
		self.actor = actor
		self.run_id = run_id
		self.extras = extras

		# Tokens allow us to reset the context var to its previous state
		# (vital for nested contexts)
		self._actor_token: Optional[Token] = None
		self._run_id_token: Optional[Token] = None
		self._extras_token: Optional[Token] = None

	def __enter__(self):
		# 1. Set Actor
		if self.actor:
			self._actor_token = _current_actor.set(self.actor)

		# 2. Set Run ID (Generate one if not provided but context is entered)
		# If the user enters a context block, they imply a distinct unit of work.
		actual_run_id = self.run_id or str(uuid.uuid4())
		self._run_id_token = _current_run_id.set(actual_run_id)

		# 3. Set Extras (Merge with existing or replace? Replace for scope usually better)
		if self.extras:
			self._extras_token = _extra_context.set(self.extras)

		# 4. Sync with OpenTelemetry
		_sync_otel_span(self.actor, actual_run_id)

		return self

	def __exit__(self, exc_type, exc_value, traceback):
		# Reset variables to what they were before the 'with' block
		if self._actor_token:
			_current_actor.reset(self._actor_token)

		if self._run_id_token:
			_current_run_id.reset(self._run_id_token)

		if self._extras_token:
			_extra_context.reset(self._extras_token)


# ==============================================================================
# Helper shorthand
# ==============================================================================


def context(actor: Optional[Actor] = None, run_id: Optional[str] = None, **kwargs) -> AmbyteContext:
	"""
	Helper function to create a context manager.
	Allows passing extras as kwargs.

	Example:
	    with ambyte.context(actor=..., model_version="v2"):
	        ...
	"""  # noqa: E101
	return AmbyteContext(actor=actor, run_id=run_id, extras=kwargs)

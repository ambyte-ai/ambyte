import inspect
import logging
from functools import wraps
from typing import Any, Callable, Union

from ambyte.client import get_client
from ambyte.exceptions import AmbyteAccessDenied

logger = logging.getLogger('ambyte.decorators')

# Type alias for the resource argument.
# It can be a static string ("urn:s3:my-bucket")
# Or a lambda function extracting it from args (lambda id, **kw: f"urn:user:{id}")
ResourceResolver = Union[str, Callable[..., str]]


def _resolve_resource(resolver: ResourceResolver, func_args: tuple, func_kwargs: dict) -> str:
	"""
	Helper to determine the actual Resource URN at runtime.
	If the resolver is a string, return it.
	If it's a callable, execute it with the function's arguments.
	"""
	if isinstance(resolver, str):
		return resolver

	if callable(resolver):
		try:
			# We pass the arguments exactly as the decorated function receives them.
			# This allows usage like: resource=lambda user_id: f"urn:user:{user_id}"
			return resolver(*func_args, **func_kwargs)
		except Exception as e:
			logger.error(f'Failed to resolve dynamic resource URN: {e}')  # pylint: disable=logging-fstring-interpolation
			return 'urn:ambyte:error:resolution_failed'

	return str(resolver)


def guard(resource: ResourceResolver, action: str = 'use', context: dict[str, Any] | None = None):
	"""
	Enforcement Decorator.

	Before the decorated function runs, it asks the Ambyte Control Plane if the
	current Actor (from ContextVars) is allowed to perform 'action' on 'resource'.

	If denied, raises AmbyteAccessDenied and prevents execution.

	Args:
	    resource: The URN of the data/asset. Can be a string or a lambda function.
	    action: The verb (e.g., "read", "write", "ai_train").
	    context: Optional dictionary of extra attributes to pass to the policy engine.

	Usage:
	    @ambyte.guard("urn:s3:sensitive", action="read")
	    def read_data(): ...

	    @ambyte.guard(lambda user_id: f"urn:user:{user_id}", action="update")
	    def update_user(user_id): ...
	"""  # noqa: E101

	def decorator(func: Callable):
		client = get_client()

		# ----------------------------------------------------------------------
		# ASYNC WRAPPER
		# ----------------------------------------------------------------------
		if inspect.iscoroutinefunction(func):

			@wraps(func)
			async def async_wrapper(*args, **kwargs):
				urn = _resolve_resource(resource, args, kwargs)

				# Non-blocking check
				allowed = await client.check_permission_async(resource_urn=urn, action=action, context=context)

				if not allowed:
					msg = f"Ambyte Policy blocked action '{action}' on '{urn}'"
					logger.warning(msg)
					raise AmbyteAccessDenied(msg)

				# Execution allowed
				return await func(*args, **kwargs)

			return async_wrapper

		# ----------------------------------------------------------------------
		# SYNC WRAPPER
		# ----------------------------------------------------------------------
		else:

			@wraps(func)
			def sync_wrapper(*args, **kwargs):
				urn = _resolve_resource(resource, args, kwargs)

				# Blocking check
				allowed = client.check_permission(resource_urn=urn, action=action, context=context)

				if not allowed:
					msg = f"Ambyte Policy blocked action '{action}' on '{urn}'"
					logger.warning(msg)
					raise AmbyteAccessDenied(msg)

				# Execution allowed
				return func(*args, **kwargs)

			return sync_wrapper

	return decorator


def audit(resource: ResourceResolver, action: str = 'use'):
	"""
	Audit-Only Decorator.

	Does NOT block execution. It simply logs that the action occurred
	(after successful execution). Useful for monitoring without enforcement risk.
	"""

	def decorator(func: Callable):
		client = get_client()

		if inspect.iscoroutinefunction(func):

			@wraps(func)
			async def async_audit_wrapper(*args, **kwargs):
				# 1. Run Logic
				result = await func(*args, **kwargs)

				# 2. Log Success (Fire and forget)
				try:
					urn = _resolve_resource(resource, args, kwargs)
					client.log_access(urn, action, allowed=True)
				except Exception:
					pass  # Never crash in audit wrapper

				return result

			return async_audit_wrapper

		@wraps(func)
		def sync_audit_wrapper(*args, **kwargs):
			# 1. Run Logic
			result = func(*args, **kwargs)

			# 2. Log Success
			try:
				urn = _resolve_resource(resource, args, kwargs)
				client.log_access(urn, action, allowed=True)
			except Exception:
				pass

			return result

		return sync_audit_wrapper

	return decorator

class AmbyteError(Exception):
	"""Base exception for all Ambyte SDK errors."""

	pass


class AmbyteConnectionError(AmbyteError):
	"""Raised when the SDK cannot connect to the Control Plane and fail_open is False."""

	pass


class AmbyteAccessDenied(AmbyteError):
	"""Raised by decorators/guards when a policy denies access."""

	pass

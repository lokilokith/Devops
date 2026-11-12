"""JIT Access module exceptions."""

from app.shared.exceptions import OpsForgeException


class JITAccessError(OpsForgeException):
    """Base exception for JIT Access."""

    pass


class GrantNotFoundError(JITAccessError):
    """Raised when a JIT access grant is not found."""

    pass


class InvalidGrantStateError(JITAccessError):
    """Raised when performing an action on a grant in an invalid state."""

    pass


class UnauthorizedActivationError(JITAccessError):
    """Raised when a user attempts to activate their own grant without permission."""

    pass

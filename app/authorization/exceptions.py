"""Authorization Engine exceptions."""

class AuthorizationError(Exception):
    """Base exception for all Authorization errors."""

class AuthorizationRepositoryError(AuthorizationError):
    """Raised when underlying repository fails."""

class AuthorizationDeniedError(AuthorizationError):
    """Raised when permission is absent."""

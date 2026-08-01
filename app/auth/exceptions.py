"""Authentication Exceptions."""


class AuthError(Exception):
    """Base exception for authentication."""


class InvalidCredentialsError(AuthError):
    """Raised when authentication fails due to invalid credentials."""


class UserInactiveError(AuthError):
    """Raised when an inactive user attempts to authenticate."""


class TokenError(AuthError):
    """Raised when token validation fails."""


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""


class TokenRevokedError(TokenError):
    """Raised when a token has been revoked."""

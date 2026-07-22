"""Custom exceptions for the Identity feature."""


class IdentityError(Exception):
    """Base exception for all identity-related errors."""


class IdentityRepositoryError(IdentityError):
    """Raised when a repository operation fails."""


class UserNotFoundError(IdentityRepositoryError):
    """Raised when the requested user cannot be found."""


class DuplicateUsernameError(IdentityRepositoryError):
    """Raised when a username already exists."""


class DuplicateEmailError(IdentityRepositoryError):
    """Raised when an email address already exists."""
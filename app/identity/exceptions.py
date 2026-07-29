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

class IdentityServiceError(IdentityError):
    """Base exception for service errors."""

class DuplicateUserError(IdentityServiceError):
    """Raised when a duplicate user (username, email, or employee_id) is detected."""

class ValidationError(IdentityServiceError):
    """Raised for general service validation errors."""
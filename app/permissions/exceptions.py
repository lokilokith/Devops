"""Custom exceptions for the Permissions module."""

class PermissionsError(Exception):
    """Base exception for all Permissions module errors."""

class PermissionsRepositoryError(PermissionsError):
    """Raised when a repository operation fails."""

class PermissionNotFoundError(PermissionsRepositoryError):
    """Raised when the requested permission cannot be found."""

class PermissionsServiceError(PermissionsError):
    """Base exception for service errors."""

class DuplicatePermissionError(PermissionsServiceError):
    """Raised when a duplicate permission is detected."""

class ValidationError(PermissionsServiceError):
    """Raised for general service validation errors."""

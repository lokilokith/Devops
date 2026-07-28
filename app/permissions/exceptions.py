"""Custom exceptions for the Permissions module."""

class PermissionsError(Exception):
    """Base exception for all Permissions module errors."""

class PermissionsRepositoryError(PermissionsError):
    """Raised when a repository operation fails."""

class PermissionNotFoundError(PermissionsRepositoryError):
    """Raised when the requested permission cannot be found."""

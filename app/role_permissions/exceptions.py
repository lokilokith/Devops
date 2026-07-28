"""Custom exceptions for RolePermissions."""

class RolePermissionsError(Exception):
    """Base exception for all RolePermissions module errors."""

class RolePermissionsRepositoryError(RolePermissionsError):
    """Raised when a repository operation fails."""

class RolePermissionNotFoundError(RolePermissionsRepositoryError):
    """Raised when the requested role-permission association cannot be found."""

class RolePermissionAlreadyExistsError(RolePermissionsRepositoryError):
    """Raised when the permission is already assigned to the role."""

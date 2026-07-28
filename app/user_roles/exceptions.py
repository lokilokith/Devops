"""Custom exceptions for UserRoles."""

class UserRolesError(Exception):
    """Base exception for all UserRoles module errors."""

class UserRolesRepositoryError(UserRolesError):
    """Raised when a repository operation fails."""

class UserRoleNotFoundError(UserRolesRepositoryError):
    """Raised when the requested user-role association cannot be found."""

class UserRoleAlreadyExistsError(UserRolesRepositoryError):
    """Raised when the role is already assigned to the user."""

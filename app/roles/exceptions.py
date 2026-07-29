"""Custom exceptions for the Roles module."""


class RolesError(Exception):
    """Base exception for all Roles module errors."""


class RolesRepositoryError(RolesError):
    """Raised when a repository operation fails."""

class RoleNotFoundError(RolesRepositoryError):
    """Raised when the requested role cannot be found."""

class RolesServiceError(RolesError):
    """Base exception for service errors."""

class DuplicateRoleError(RolesServiceError):
    """Raised when a duplicate role is detected."""

class ValidationError(RolesServiceError):
    """Raised for general service validation errors."""
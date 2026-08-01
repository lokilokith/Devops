"""Custom exceptions for the Resources module."""

from app.shared.exceptions import (
    ResourceNotFoundException as GlobalResourceNotFoundException,
)


class ResourcesError(Exception):
    """Base exception for all Resources module errors."""


class ResourcesRepositoryError(ResourcesError):
    """Raised when a repository operation fails."""


class ResourceNotFoundError(GlobalResourceNotFoundException, ResourcesRepositoryError):
    """Raised when the requested resource cannot be found."""


class ResourcesServiceError(ResourcesError):
    """Base exception for service errors."""


class DuplicateResourceError(ResourcesServiceError):
    """Raised when a duplicate resource is detected."""


class ValidationError(ResourcesServiceError):
    """Raised for general service validation errors."""

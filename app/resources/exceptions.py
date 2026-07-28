"""Custom exceptions for the Resources module."""

class ResourcesError(Exception):
    """Base exception for all Resources module errors."""

class ResourcesRepositoryError(ResourcesError):
    """Raised when a repository operation fails."""

class ResourceNotFoundError(ResourcesRepositoryError):
    """Raised when the requested resource cannot be found."""

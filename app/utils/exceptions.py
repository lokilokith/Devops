"""OpsForge Custom Business Exceptions.

Defines domain-specific business, validation, configuration,
and database exceptions.
"""

from typing import Any


class OpsForgeException(Exception):
    """Base exception class for all OpsForge domain errors."""

    pass


class ValidationException(OpsForgeException):
    """Raised when input validation rules are violated (HTTP 400)."""

    def __init__(
        self,
        message: str,
        errors: list[Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


class ResourceNotFoundException(OpsForgeException):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidStatusTransition(OpsForgeException):
    """Raised when an illegal status change is requested."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DatabaseOperationException(OpsForgeException):
    """Raised when database operations fail (HTTP 500)."""

    def __init__(
        self,
        message: str,
        errors: list[Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


class DatabaseException(DatabaseOperationException):
    """Legacy alias for database persistence failures (HTTP 500)."""

    pass


class ConfigurationException(OpsForgeException):
    """Raised when bootstrap configurations are invalid or missing."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

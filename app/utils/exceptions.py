"""OpsForge Custom Business Exceptions.

Defines domain-specific business, validation, configuration, and database exceptions.
"""
from typing import Any


class OpsForgeException(Exception):
    """Base exception class for all OpsForge domain errors."""

    pass


class ValidationException(OpsForgeException):
    """Raised when input validation rules are violated (HTTP 400)."""

    def __init__(self,message: str,errors: list[Any] | None = None,):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


class ThreatNotFoundException(OpsForgeException):
    """Raised when a requested Threat record does not exist (HTTP 404)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ResourceNotFoundException(ThreatNotFoundException):
    """Legacy alias raised when a requested resource is not found.

    Returns HTTP 404.
    """

    pass


class InvalidStatusTransition(OpsForgeException):
    """Raised when an illegal status change is requested."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DatabaseOperationException(OpsForgeException):
    """Raised when database commit, rollback, or query operations fail (HTTP 500)."""

    def __init__(self,message: str,errors: list[Any] | None = None,):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


class DatabaseException(DatabaseOperationException):
    """Legacy alias or subclass for database-related persistence failures (HTTP 500)."""

    pass


class ConfigurationException(OpsForgeException):
    """Raised when application bootstrap configurations are invalid or missing."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


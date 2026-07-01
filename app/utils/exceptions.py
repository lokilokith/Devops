"""OpsForge Custom Business Exceptions.

Defines domain-specific business and validation exceptions raised by the Service layer.
"""


class OpsForgeException(Exception):
    """Base exception class for all OpsForge domain errors."""

    pass


class ValidationException(OpsForgeException):
    """Raised when input validation rules are violated."""

    pass


class ThreatNotFoundException(OpsForgeException):
    """Raised when a requested Threat record does not exist."""

    pass


class InvalidStatusTransition(OpsForgeException):
    """Raised when an illegal status change is requested."""

    pass


class DatabaseOperationException(OpsForgeException):
    """Raised when database commit or rollback operations fail."""

    pass

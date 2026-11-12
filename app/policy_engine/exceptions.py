"""Exceptions for the Policy Engine module."""

from app.shared.exceptions import OpsForgeException


class PolicyEngineError(OpsForgeException):
    """Base exception for policy engine errors."""

    pass


class PolicyNotFoundError(PolicyEngineError):
    """Raised when a requested policy is not found."""

    pass


class PolicyValidationError(PolicyEngineError):
    """Raised when policy conditions or attributes are invalid."""

    pass


class PolicyRepositoryError(PolicyEngineError):
    """Raised when a repository operation fails."""

    pass


class PolicyEvaluationError(PolicyEngineError):
    """Raised when policy evaluation fails unexpectedly."""

    pass

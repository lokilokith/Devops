"""Custom exceptions for Access Requests."""


class AccessRequestsError(Exception):
    """Base exception for all Access Requests module errors."""


class AccessRequestRepositoryError(AccessRequestsError):
    """Raised when a repository operation fails."""


class AccessRequestNotFoundError(AccessRequestRepositoryError):
    """Raised when the requested access request cannot be found."""


class AccessRequestInvalidStateError(AccessRequestsError):
    """Raised when the request state transition is invalid."""


class AccessRequestDuplicateError(AccessRequestsError):
    """Raised when an active request already exists."""


class AccessRequestValidationError(AccessRequestsError):
    """Raised when business logic validation fails."""

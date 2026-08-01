"""Exceptions for Audit"""


class AuditError(Exception):
    """Base exception for all Audit module errors."""


class AuditRepositoryError(AuditError):
    """Raised when a repository operation fails."""


class AuditNotFoundError(AuditRepositoryError):
    """Raised when the requested audit log cannot be found."""

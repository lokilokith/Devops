"""Vault‑specific exception definitions.

This module provides exceptions used by the vault persistence layer.
"""

class ConcurrencyError(RuntimeError):
    """Raised when an optimistic‑concurrency check fails (row_version mismatch)."""

class InvalidSecretStateError(ValueError):
    """Raised when a secret is in an invalid state for the requested operation."""

class SecretCheckedOutError(InvalidSecretStateError):
    """Raised when an operation cannot proceed because the secret is checked out."""

"""Vault-specific exception definitions.

This module provides exceptions used by the vault persistence and domain layer.
"""


class VaultException(Exception):
    """Base exception for all vault plane operations."""


class ConcurrencyError(VaultException, RuntimeError):
    """Raised when an optimistic-concurrency check fails (row_version mismatch)."""


class InvalidSecretStateError(VaultException, ValueError):
    """Raised when a secret is in an invalid state for the requested operation."""


class SecretCheckedOutError(InvalidSecretStateError):
    """Raised when an operation cannot proceed because the secret is checked out."""

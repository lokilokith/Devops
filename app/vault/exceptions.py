"""Vault‑specific exception definitions.

This module provides exceptions used by the vault persistence layer.
"""

class ConcurrencyError(RuntimeError):
    """Raised when an optimistic‑concurrency check fails (row_version mismatch)."""

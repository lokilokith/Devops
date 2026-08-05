"""Vault Exceptions."""

from __future__ import annotations

from app.shared.exceptions import DomainException


class DecryptionFailedError(DomainException):
    """Raised when AES-GCM tag verification fails or DEK decryption fails."""
    pass

class MasterKeyUnavailableError(DomainException):
    """Raised when the KMS provider is unreachable."""
    pass

class InvalidKeyVersionError(DomainException):
    """Raised when an unsupported or revoked MEK version is requested."""
    pass

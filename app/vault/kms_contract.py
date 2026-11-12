"""KMS Contract Stub and Protocol Validation (Gate 1).

Defines the KMS contract verification utility and deterministic KMS test double
required by Gate 1 of the OpsForge Canonical Master Plan.
"""

from __future__ import annotations

import base64
from typing import Any, Optional, Set

from app.vault.crypto import KMSProviderError


def validate_kms_contract(provider: Any) -> bool:
    """Validate that a candidate provider satisfies the KMSProvider contract.

    Verifies the presence and callable nature of all four required methods:
    - encrypt_dek(plaintext_dek, key_version, aad) -> bytes
    - decrypt_dek(encrypted_dek, key_version, aad) -> bytes
    - get_active_key_version() -> str
    - supports_key_version(key_version) -> bool

    Raises:
        TypeError: If provider does not implement the full KMSProvider protocol.
    """
    required_methods = [
        "encrypt_dek",
        "decrypt_dek",
        "get_active_key_version",
        "supports_key_version",
    ]
    for method_name in required_methods:
        attr = getattr(provider, method_name, None)
        if not callable(attr):
            raise TypeError(
                f"KMS provider {type(provider).__name__} violates contract: "
                f"missing callable '{method_name}'"
            )
    return True


class StubKMSProvider:
    """Deterministic, in-memory KMS contract stub for testing and contract verification."""

    def __init__(
        self,
        active_version: str = "v1",
        supported_versions: Optional[Set[str]] = None,
    ) -> None:
        self._active_version = active_version
        self._supported_versions = supported_versions or {active_version}
        self._key = b"\x00" * 32

    def get_active_key_version(self) -> str:
        """Return the active master key version."""
        return self._active_version

    def supports_key_version(self, key_version: str) -> bool:
        """Return True if the key version is supported."""
        return key_version in self._supported_versions

    def encrypt_dek(self, plaintext_dek: bytes, key_version: str, aad: bytes) -> bytes:
        """Opaquely wrap DEK with deterministic prefix and key version."""
        if not self.supports_key_version(key_version):
            raise KMSProviderError(f"Unsupported key version: {key_version}")
        # Deterministic reversible envelope for test stub
        return (
            b"STUB_ENCRYPTED:"
            + key_version.encode()
            + b":"
            + base64.b64encode(plaintext_dek)
        )

    def decrypt_dek(self, encrypted_dek: bytes, key_version: str, aad: bytes) -> bytes:
        """Unwrap DEK if version is supported and format matches."""
        if not self.supports_key_version(key_version):
            raise KMSProviderError(f"Unsupported key version: {key_version}")
        prefix = b"STUB_ENCRYPTED:" + key_version.encode() + b":"
        if not encrypted_dek.startswith(prefix):
            raise KMSProviderError("Invalid encrypted DEK envelope for stub provider")
        encoded_dek = encrypted_dek[len(prefix) :]
        return base64.b64decode(encoded_dek)

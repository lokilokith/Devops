"""Host Key Verification module for OpsForge Execution Plane.

Implements strict, fail-closed SSH host identity verification:
- Strict matching against registered host key fingerprints (SHA256) or raw public keys.
- Host key mismatch detection.
- Absolute rejection of auto-add or blind-trust policies.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Optional


class HostKeyVerificationError(Exception):
    """Raised when host key verification fails or detects a mismatch."""

    pass


class HostKeyMismatchError(HostKeyVerificationError):
    """Raised specifically when presented host key does not match registered trusted key."""

    pass


class UntrustedHostError(HostKeyVerificationError):
    """Raised when connecting to a host without pre-registered trust."""

    pass


@dataclass(frozen=True)
class TrustedHostKey:
    """Registered trusted host identity."""

    host: str
    key_type: str  # e.g., 'ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256'
    key_base64: str
    fingerprint_sha256: str


class HostKeyVerifier:
    """Strict host key verifier ensuring zero MITM vulnerability."""

    def __init__(self, trusted_keys: dict[str, TrustedHostKey] | None = None) -> None:
        """Initialize verifier with mapping of hostname/IP to TrustedHostKey."""
        self._trusted_keys: dict[str, TrustedHostKey] = dict(trusted_keys or {})

    def register_trusted_key(
        self,
        host: str,
        key_type: str,
        key_base64: str,
    ) -> TrustedHostKey:
        """Register or update a trusted host key.

        Args:
            host: Target hostname or IP.
            key_type: SSH key type (e.g. 'ssh-ed25519').
            key_base64: Base64-encoded public key data.

        Returns:
            TrustedHostKey object with computed SHA256 fingerprint.
        """
        host = host.strip()
        key_type = key_type.strip()
        key_base64 = key_base64.strip()

        # Validate base64 data
        try:
            raw_key_bytes = base64.b64decode(key_base64)
        except Exception as e:
            raise HostKeyVerificationError(
                f"Invalid base64 key data for {host}: {e}"
            ) from e

        fingerprint = self.compute_sha256_fingerprint(raw_key_bytes)
        trusted = TrustedHostKey(
            host=host,
            key_type=key_type,
            key_base64=key_base64,
            fingerprint_sha256=fingerprint,
        )
        self._trusted_keys[host] = trusted
        return trusted

    def get_trusted_key(self, host: str) -> Optional[TrustedHostKey]:
        """Get registered key for host."""
        return self._trusted_keys.get(host.strip())

    @staticmethod
    def compute_sha256_fingerprint(raw_key_bytes: bytes) -> str:
        """Compute standard OpenSSH SHA256 fingerprint from raw key bytes (SHA256:<base64-no-padding>)."""
        digest = hashlib.sha256(raw_key_bytes).digest()
        b64_digest = base64.b64encode(digest).decode("ascii").rstrip("=")
        return f"SHA256:{b64_digest}"

    def verify(
        self,
        host: str,
        presented_key_type: str,
        presented_key_bytes: bytes,
    ) -> bool:
        """Verify presented host key against registered trusted key.

        Args:
            host: Target host string.
            presented_key_type: Key type received during SSH handshake.
            presented_key_bytes: Raw public key bytes received during SSH handshake.

        Returns:
            True if key matches registered trusted key.

        Raises:
            UntrustedHostError: If host is not registered.
            HostKeyMismatchError: If presented key does not match trusted record.
        """
        host = host.strip()
        trusted = self.get_trusted_key(host)

        if not trusted:
            raise UntrustedHostError(
                f"Untrusted target host '{host}'. No registered host key found. Connection rejected."
            )

        presented_fingerprint = self.compute_sha256_fingerprint(presented_key_bytes)
        presented_base64 = base64.b64encode(presented_key_bytes).decode("ascii")

        # Verify key type
        if trusted.key_type != presented_key_type:
            raise HostKeyMismatchError(
                f"Host key type mismatch for '{host}': expected {trusted.key_type}, got {presented_key_type}"
            )

        # Verify fingerprint and raw base64
        if (
            trusted.fingerprint_sha256 != presented_fingerprint
            or trusted.key_base64 != presented_base64
        ):
            raise HostKeyMismatchError(
                f"HOST KEY MISMATCH DETECTED for '{host}'! "
                f"Expected fingerprint {trusted.fingerprint_sha256}, got {presented_fingerprint}. "
                "Possible Man-in-the-Middle attack. Connection aborted."
            )

        return True

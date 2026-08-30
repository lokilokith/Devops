"""Unit tests for HostKeyVerifier and strict host identity checks."""

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.execution.host_identity import (
    HostKeyMismatchError,
    HostKeyVerificationError,
    HostKeyVerifier,
    TrustedHostKey,
    UntrustedHostError,
)


def _generate_test_ed25519_key_bytes() -> tuple[bytes, str]:
    """Generate raw OpenSSH ed25519 public key bytes and base64 string."""
    key = ed25519.Ed25519PrivateKey.generate()
    raw_pub = key.public_key().public_bytes_raw()
    # Format OpenSSH wire format for ed25519: [string "ssh-ed25519"][string key_bytes]
    wire_format = (
        len(b"ssh-ed25519").to_bytes(4, byteorder="big")
        + b"ssh-ed25519"
        + len(raw_pub).to_bytes(4, byteorder="big")
        + raw_pub
    )
    b64_str = base64.b64encode(wire_format).decode("ascii")
    return wire_format, b64_str


def test_host_key_verifier_register_and_verify():
    """Test registering a trusted host key and successful verification."""
    raw_bytes, b64_str = _generate_test_ed25519_key_bytes()

    verifier = HostKeyVerifier()
    trusted = verifier.register_trusted_key(
        host="opsforge-target.internal",
        key_type="ssh-ed25519",
        key_base64=b64_str,
    )

    assert isinstance(trusted, TrustedHostKey)
    assert trusted.host == "opsforge-target.internal"
    assert trusted.key_type == "ssh-ed25519"
    assert trusted.key_base64 == b64_str
    assert trusted.fingerprint_sha256.startswith("SHA256:")

    # Verify identical presented key
    assert verifier.verify("opsforge-target.internal", "ssh-ed25519", raw_bytes) is True


def test_host_key_verifier_untrusted_host():
    """Test connecting to an un-registered host raises UntrustedHostError."""
    raw_bytes, _ = _generate_test_ed25519_key_bytes()
    verifier = HostKeyVerifier()

    with pytest.raises(UntrustedHostError, match="Untrusted target host"):
        verifier.verify("unknown-host.internal", "ssh-ed25519", raw_bytes)


def test_host_key_verifier_key_mismatch():
    """Test MITM or host key mismatch raises HostKeyMismatchError."""
    raw_bytes_trusted, b64_trusted = _generate_test_ed25519_key_bytes()
    raw_bytes_attacker, _ = _generate_test_ed25519_key_bytes()

    verifier = HostKeyVerifier()
    verifier.register_trusted_key(
        host="opsforge-target.internal",
        key_type="ssh-ed25519",
        key_base64=b64_trusted,
    )

    # Presenting attacker's key must raise HostKeyMismatchError
    with pytest.raises(HostKeyMismatchError, match="HOST KEY MISMATCH DETECTED"):
        verifier.verify("opsforge-target.internal", "ssh-ed25519", raw_bytes_attacker)


def test_host_key_verifier_type_mismatch():
    """Test key type mismatch raises HostKeyMismatchError."""
    raw_bytes, b64_str = _generate_test_ed25519_key_bytes()

    verifier = HostKeyVerifier()
    verifier.register_trusted_key(
        host="opsforge-target.internal",
        key_type="ssh-ed25519",
        key_base64=b64_str,
    )

    with pytest.raises(HostKeyMismatchError, match="Host key type mismatch"):
        verifier.verify("opsforge-target.internal", "ssh-rsa", raw_bytes)


def test_host_key_verifier_invalid_base64_registration():
    """Test registering invalid base64 data raises HostKeyVerificationError."""
    verifier = HostKeyVerifier()
    with pytest.raises(HostKeyVerificationError, match="Invalid base64 key data"):
        verifier.register_trusted_key(
            host="bad-key.internal",
            key_type="ssh-ed25519",
            key_base64="!!!NOT_VALID_BASE64!!!",
        )

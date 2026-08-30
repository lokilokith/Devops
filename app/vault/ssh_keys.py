"""Cryptographic utilities for SSH key generation and manipulation.

Generates and manipulates Ed25519 SSH keypairs strictly in memory within the
protected Vault plane boundary. Plaintext private keys are never persisted to
temporary files or exposed in logs.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_ed25519_keypair(comment: str = "opsforge-key") -> Tuple[str, str]:
    """Generate an Ed25519 private/public keypair in memory.

    Returns:
        tuple[str, str]: (private_key_pem, openssh_public_key)
    """
    private_key = ed25519.Ed25519PrivateKey.generate()

    # Serialize private key in OpenSSH format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Serialize public key in OpenSSH format
    public_key = private_key.public_key()
    public_ssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")

    if comment:
        public_ssh = f"{public_ssh.strip()} {comment}"

    return private_pem, public_ssh


def extract_public_key(private_key_pem: str, comment: str = "opsforge-key") -> str:
    """Extract the OpenSSH public key line from a private key PEM string in memory."""
    if not private_key_pem or not isinstance(private_key_pem, str):
        raise ValueError("Invalid private key PEM: must be a non-empty string.")

    try:
        private_key = serialization.load_ssh_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )
    except Exception as e:
        raise ValueError(f"Failed to load SSH private key: {e}") from e

    public_key = private_key.public_key()
    public_ssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")

    if comment:
        public_ssh = f"{public_ssh.strip()} {comment}"

    return public_ssh


def compute_key_fingerprint(key_material: str) -> str:
    """Compute SHA256 fingerprint for OpenSSH public key or private key PEM."""
    if not key_material or not isinstance(key_material, str):
        raise ValueError("Key material must be a non-empty string.")

    cleaned = key_material.strip()
    if cleaned.startswith("-----BEGIN"):
        # Extract public key first
        public_ssh = extract_public_key(cleaned, comment="")
    else:
        public_ssh = cleaned

    parts = public_ssh.split()
    if len(parts) < 2:
        raise ValueError("Invalid OpenSSH public key format")

    raw_bytes = base64.b64decode(parts[1])
    digest = hashlib.sha256(raw_bytes).digest()
    fp_b64 = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{fp_b64}"

"""Vault Cryptographic Primitives and Key Provider Protocol."""

from __future__ import annotations

import base64
import os
from typing import Protocol, Tuple
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault.domain import SecretMetadata


class MasterKeyProvider(Protocol):
    """Abstract interface for Master Key operations."""

    def encrypt_dek(self, plaintext_dek: bytes, key_version: str, aad: bytes) -> bytes:
        ...

    def decrypt_dek(self, encrypted_dek: bytes, key_version: str, aad: bytes) -> bytes:
        ...

    def get_active_key_version(self) -> str:
        ...

    def supports_key_version(self, key_version: str) -> bool:
        ...


class LocalEnvironmentKeyProvider:
    """Master Key Provider that loads AES-256 key from VAULT_MASTER_KEY env var."""

    def __init__(self) -> None:
        key_b64 = os.environ.get("VAULT_MASTER_KEY")
        if not key_b64:
            raise ValueError("VAULT_MASTER_KEY environment variable is not set")

        try:
            self._key = base64.b64decode(key_b64)
        except Exception as e:
            raise ValueError(f"VAULT_MASTER_KEY is not a valid base64 string: {e}")

        if len(self._key) != 32:
            raise ValueError(f"VAULT_MASTER_KEY must be exactly 32 bytes for AES-256 (got {len(self._key)})")

        self._active_version = "v1"

    def encrypt_dek(self, plaintext_dek: bytes, key_version: str, aad: bytes) -> bytes:
        if not self.supports_key_version(key_version):
            raise ValueError(f"Unsupported master key version: {key_version}")

        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext_dek, aad)

        # Prepend the nonce to the ciphertext for storage
        return nonce + ciphertext

    def decrypt_dek(self, encrypted_dek: bytes, key_version: str, aad: bytes) -> bytes:
        if not self.supports_key_version(key_version):
            raise ValueError(f"Unsupported master key version: {key_version}")

        if len(encrypted_dek) < 28: # 12 (nonce) + 16 (tag)
            raise ValueError("Encrypted DEK is too short")

        aesgcm = AESGCM(self._key)
        nonce = encrypted_dek[:12]
        ciphertext = encrypted_dek[12:]

        # This will raise cryptography.exceptions.InvalidTag if tampered or AAD mismatch
        return aesgcm.decrypt(nonce, ciphertext, aad)

    def get_active_key_version(self) -> str:
        return self._active_version

    def supports_key_version(self, key_version: str) -> bool:
        return key_version == self._active_version


class EncryptionService:
    """Domain service for handling envelope encryption lifecycles."""

    def __init__(self, key_provider: MasterKeyProvider):
        self._provider = key_provider

    def _generate_aad(self, resource_id: UUID, secret_id: UUID) -> bytes:
        """Construct deterministic AAD."""
        return f"opsforge:v1:{resource_id}:{secret_id}".encode("utf-8")

    def encrypt_payload(
        self, resource_id: UUID, secret_id: UUID, plaintext: bytes
    ) -> Tuple[bytes, bytes, SecretMetadata]:
        """
        Encrypts a payload using envelope encryption.
        Returns: (encrypted_dek, encrypted_payload, SecretMetadata)
        """
        # 1. Generate DEK
        dek = os.urandom(32)

        # 2. Generate AAD
        aad = self._generate_aad(resource_id, secret_id)

        # 3. Wrap DEK with Master Key
        key_version = self._provider.get_active_key_version()
        encrypted_dek = self._provider.encrypt_dek(dek, key_version, aad)

        # 4. Encrypt Payload with DEK
        aesgcm = AESGCM(dek)
        payload_nonce = os.urandom(12)
        encrypted_payload = aesgcm.encrypt(payload_nonce, plaintext, aad)

        # 5. Build Metadata
        metadata = SecretMetadata(
            key_version=key_version,
            algorithm="AES-256-GCM",
            nonce=base64.b64encode(payload_nonce).decode("utf-8"),
            encryption_context={
                "resource_id": str(resource_id),
                "secret_id": str(secret_id),
            }
        )

        return encrypted_dek, encrypted_payload, metadata

    def decrypt_payload(
        self,
        resource_id: UUID,
        secret_id: UUID,
        encrypted_dek: bytes,
        encrypted_payload: bytes,
        metadata: SecretMetadata
    ) -> bytes:
        """
        Decrypts a payload using envelope encryption.
        """
        if metadata.algorithm != "AES-256-GCM":
            raise ValueError(f"Unsupported algorithm: {metadata.algorithm}")

        # 1. Generate AAD
        aad = self._generate_aad(resource_id, secret_id)

        # 2. Verify and decode payload nonce
        try:
            payload_nonce = base64.b64decode(metadata.nonce)
        except Exception as e:
            raise ValueError(f"Invalid nonce encoding: {e}")

        # 3. Unwrap DEK
        dek = self._provider.decrypt_dek(encrypted_dek, metadata.key_version, aad)

        # 4. Decrypt Payload
        aesgcm = AESGCM(dek)
        return aesgcm.decrypt(payload_nonce, encrypted_payload, aad)

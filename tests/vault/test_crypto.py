import base64
import os
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag

from app.vault.crypto import EncryptionService, LocalEnvironmentKeyProvider


@pytest.fixture
def valid_mek_b64() -> str:
    """Generate a random 32-byte key base64 encoded for testing."""
    return base64.b64encode(os.urandom(32)).decode("utf-8")


@pytest.fixture
def mock_env(monkeypatch, valid_mek_b64):
    monkeypatch.setenv("VAULT_MASTER_KEY", valid_mek_b64)
    return valid_mek_b64


@pytest.fixture
def key_provider(mock_env):
    return LocalEnvironmentKeyProvider()


@pytest.fixture
def encryption_service(key_provider):
    return EncryptionService(key_provider)


def test_provider_initialization_failures(monkeypatch):
    monkeypatch.delenv("VAULT_MASTER_KEY", raising=False)
    with pytest.raises(ValueError, match="is not set"):
        LocalEnvironmentKeyProvider()

    monkeypatch.setenv("VAULT_MASTER_KEY", "not-base64-&*(")
    with pytest.raises(ValueError, match="is not a valid base64 string"):
        LocalEnvironmentKeyProvider()

    # Base64 for a 16-byte key (needs to be 32)
    short_key = base64.b64encode(os.urandom(16)).decode("utf-8")
    monkeypatch.setenv("VAULT_MASTER_KEY", short_key)
    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        LocalEnvironmentKeyProvider()


def test_key_version_validation(key_provider):
    assert key_provider.supports_key_version("v1") is True
    assert key_provider.supports_key_version("v2") is False

    with pytest.raises(ValueError, match="Unsupported master key version"):
        key_provider.encrypt_dek(b"dek", "v2", b"aad")

    with pytest.raises(ValueError, match="Unsupported master key version"):
        key_provider.decrypt_dek(b"dek", "v2", b"aad")


def test_normal_encryption_flow(encryption_service):
    resource_id = uuid4()
    secret_id = uuid4()
    plaintext = b"super-secret-password-123"

    encrypted_dek, encrypted_payload, metadata = encryption_service.encrypt_payload(
        resource_id, secret_id, plaintext
    )

    assert encrypted_dek is not None
    assert encrypted_payload is not None
    assert metadata.algorithm == "AES-256-GCM"
    assert metadata.key_version == "v1"

    decrypted = encryption_service.decrypt_payload(
        resource_id, secret_id, encrypted_dek, encrypted_payload, metadata
    )
    assert decrypted == plaintext


def test_aad_tampering(encryption_service):
    resource_id = uuid4()
    secret_id = uuid4()
    plaintext = b"super-secret-password-123"

    encrypted_dek, encrypted_payload, metadata = encryption_service.encrypt_payload(
        resource_id, secret_id, plaintext
    )

    # Tamper with AAD by passing a different resource_id
    wrong_resource_id = uuid4()
    with pytest.raises(InvalidTag):
        encryption_service.decrypt_payload(
            wrong_resource_id, secret_id, encrypted_dek, encrypted_payload, metadata
        )


def test_ciphertext_tampering(encryption_service):
    resource_id = uuid4()
    secret_id = uuid4()
    plaintext = b"super-secret-password-123"

    encrypted_dek, encrypted_payload, metadata = encryption_service.encrypt_payload(
        resource_id, secret_id, plaintext
    )

    # Tamper with the encrypted payload
    tampered_payload = bytearray(encrypted_payload)
    tampered_payload[0] ^= 0xFF

    with pytest.raises(InvalidTag):
        encryption_service.decrypt_payload(
            resource_id, secret_id, encrypted_dek, bytes(tampered_payload), metadata
        )

    # Tamper with the DEK
    tampered_dek = bytearray(encrypted_dek)
    tampered_dek[0] ^= 0xFF

    with pytest.raises(InvalidTag):
        encryption_service.decrypt_payload(
            resource_id, secret_id, bytes(tampered_dek), encrypted_payload, metadata
        )


def test_nonce_uniqueness(encryption_service):
    resource_id = uuid4()
    secret_id = uuid4()
    plaintext = b"super-secret-password-123"

    _, enc1, meta1 = encryption_service.encrypt_payload(
        resource_id, secret_id, plaintext
    )
    _, enc2, meta2 = encryption_service.encrypt_payload(
        resource_id, secret_id, plaintext
    )

    # Ciphertexts should be completely different due to different random DEK and nonces
    assert enc1 != enc2
    assert meta1.nonce != meta2.nonce


def test_wrong_master_key(monkeypatch):
    # Setup Provider A
    mek_a = base64.b64encode(os.urandom(32)).decode("utf-8")
    monkeypatch.setenv("VAULT_MASTER_KEY", mek_a)
    provider_a = LocalEnvironmentKeyProvider()
    service_a = EncryptionService(provider_a)

    # Encrypt with A
    resource_id = uuid4()
    secret_id = uuid4()
    enc_dek, enc_payload, meta = service_a.encrypt_payload(
        resource_id, secret_id, b"plaintext"
    )

    # Setup Provider B
    mek_b = base64.b64encode(os.urandom(32)).decode("utf-8")
    monkeypatch.setenv("VAULT_MASTER_KEY", mek_b)
    provider_b = LocalEnvironmentKeyProvider()
    service_b = EncryptionService(provider_b)

    # Attempt decrypt with B
    with pytest.raises(InvalidTag):
        service_b.decrypt_payload(resource_id, secret_id, enc_dek, enc_payload, meta)

"""Tests for KMS Contract Stub and Protocol Validation (Gate 1)."""

import pytest

from app.vault.crypto import KMSProviderError
from app.vault.kms_contract import StubKMSProvider, validate_kms_contract


def test_stub_kms_provider_satisfies_contract():
    stub = StubKMSProvider(active_version="v1")
    assert validate_kms_contract(stub) is True


def test_stub_kms_provider_encrypt_decrypt_roundtrip():
    stub = StubKMSProvider(active_version="v1", supported_versions={"v1", "v2"})
    plaintext_dek = b"thirty-two-bytes-secret-dek-1234"
    aad = b"resource:123"

    encrypted_dek = stub.encrypt_dek(plaintext_dek, "v1", aad)
    assert isinstance(encrypted_dek, bytes)
    assert encrypted_dek != plaintext_dek
    assert encrypted_dek.startswith(b"STUB_ENCRYPTED:v1:")

    decrypted_dek = stub.decrypt_dek(encrypted_dek, "v1", aad)
    assert decrypted_dek == plaintext_dek


def test_stub_kms_provider_unsupported_version_rejected():
    stub = StubKMSProvider(active_version="v1", supported_versions={"v1"})
    with pytest.raises(KMSProviderError, match="Unsupported key version"):
        stub.encrypt_dek(b"dek", "v99", b"aad")

    with pytest.raises(KMSProviderError, match="Unsupported key version"):
        stub.decrypt_dek(b"STUB_ENCRYPTED:v99:payload", "v99", b"aad")


def test_validate_kms_contract_rejects_incomplete_provider():
    class IncompleteProvider:
        def encrypt_dek(self, plaintext_dek, key_version, aad):
            return b"encrypted"

    with pytest.raises(TypeError, match="violates contract"):
        validate_kms_contract(IncompleteProvider())

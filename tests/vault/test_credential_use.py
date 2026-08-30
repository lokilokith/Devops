"""Tests for Narrow Authorized Credential-Use Operation (Master Plan Item 14.1)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.vault.credential_use import (
    CredentialUseContext,
    CredentialUseService,
    UnauthorizedCredentialUseError,
)
from app.vault.domain import Secret, SecretMetadata, SecretVersion
from app.vault.exceptions import VaultException


@pytest.fixture
def credential_use_service():
    mock_vault_repo = MagicMock()
    mock_encryption_svc = MagicMock()
    mock_encryption_svc.decrypt_payload.return_value = (
        b"ephemeral-plaintext-password-123"
    )
    svc = CredentialUseService(mock_vault_repo, mock_encryption_svc)
    return svc, mock_vault_repo, mock_encryption_svc


def test_acquire_ephemeral_credential_success(credential_use_service):
    svc, mock_repo, mock_enc = credential_use_service

    user_id = uuid4()
    resource_id = uuid4()
    credential_id = uuid4()
    now = datetime.now(timezone.utc)

    # Set up mock secret bound to the resource
    mock_secret = MagicMock(spec=Secret)
    mock_secret.id = credential_id
    mock_secret.resource_id = resource_id
    mock_version = MagicMock(spec=SecretVersion)
    mock_version.encrypted_dek = b"enc_dek"
    mock_version.encrypted_payload = b"enc_payload"
    mock_version.metadata = SecretMetadata("v1", "AES", "nonce", {})
    mock_secret.current_version = mock_version
    mock_repo.find_by_id.return_value = mock_secret

    context = CredentialUseContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=credential_id,
        session_id=uuid4(),
        grant_id=uuid4(),
        target_account_binding_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    plaintext = svc.acquire_ephemeral_credential(context)
    assert plaintext == b"ephemeral-plaintext-password-123"
    mock_repo.find_by_id.assert_called_once_with(credential_id)
    mock_enc.decrypt_payload.assert_called_once()


def test_acquire_ephemeral_credential_unbound_resource_rejected(credential_use_service):
    svc, mock_repo, mock_enc = credential_use_service

    user_id = uuid4()
    requested_resource_id = uuid4()
    different_actual_resource_id = uuid4()
    credential_id = uuid4()
    now = datetime.now(timezone.utc)

    # Secret is bound to a DIFFERENT resource
    mock_secret = MagicMock(spec=Secret)
    mock_secret.id = credential_id
    mock_secret.resource_id = different_actual_resource_id
    mock_repo.find_by_id.return_value = mock_secret

    context = CredentialUseContext(
        user_id=user_id,
        resource_id=requested_resource_id,
        credential_id=credential_id,
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    with pytest.raises(
        UnauthorizedCredentialUseError, match="is not bound to resource"
    ):
        svc.acquire_ephemeral_credential(context)

    # Invariant: Decryption must never be attempted if binding check fails
    mock_enc.decrypt_payload.assert_not_called()


def test_acquire_ephemeral_credential_expired_context_rejected(credential_use_service):
    svc, mock_repo, mock_enc = credential_use_service

    user_id = uuid4()
    resource_id = uuid4()
    credential_id = uuid4()
    now = datetime.now(timezone.utc)

    context = CredentialUseContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=credential_id,
        requested_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )

    with pytest.raises(UnauthorizedCredentialUseError, match="has expired"):
        svc.acquire_ephemeral_credential(context)

    mock_repo.find_by_id.assert_not_called()
    mock_enc.decrypt_payload.assert_not_called()


def test_context_validation_missing_fields():
    now = datetime.now(timezone.utc)
    with pytest.raises(UnauthorizedCredentialUseError, match="user_id is required"):
        ctx = CredentialUseContext(
            user_id=None,  # type: ignore[arg-type]
            resource_id=uuid4(),
            credential_id=uuid4(),
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()

    with pytest.raises(UnauthorizedCredentialUseError, match="resource_id is required"):
        ctx = CredentialUseContext(
            user_id=uuid4(),
            resource_id=None,  # type: ignore[arg-type]
            credential_id=uuid4(),
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()

    with pytest.raises(
        UnauthorizedCredentialUseError, match="credential_id is required"
    ):
        ctx = CredentialUseContext(
            user_id=uuid4(),
            resource_id=uuid4(),
            credential_id=None,  # type: ignore[arg-type]
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()

    with pytest.raises(
        UnauthorizedCredentialUseError, match="requested_at is after expires_at"
    ):
        ctx = CredentialUseContext(
            user_id=uuid4(),
            resource_id=uuid4(),
            credential_id=uuid4(),
            requested_at=now + timedelta(hours=2),
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()


def test_acquire_ephemeral_credential_secret_not_found(credential_use_service):
    svc, mock_repo, _ = credential_use_service
    mock_repo.find_by_id.return_value = None

    now = datetime.now(timezone.utc)
    context = CredentialUseContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )

    with pytest.raises(UnauthorizedCredentialUseError, match="not found"):
        svc.acquire_ephemeral_credential(context)


def test_acquire_ephemeral_credential_missing_version(credential_use_service):
    svc, mock_repo, _ = credential_use_service
    user_id = uuid4()
    resource_id = uuid4()
    credential_id = uuid4()

    mock_secret = MagicMock(spec=Secret)
    mock_secret.id = credential_id
    mock_secret.resource_id = resource_id
    mock_secret.current_version = None
    mock_repo.find_by_id.return_value = mock_secret

    now = datetime.now(timezone.utc)
    context = CredentialUseContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=credential_id,
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )

    with pytest.raises(VaultException, match="No active secret version found"):
        svc.acquire_ephemeral_credential(context)

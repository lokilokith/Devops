"""Tests for Narrow Authorized Credential-Use Operation (Master Plan Item 14.1)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.vault.credential_use import (
    CredentialUseContext,
    CredentialUseService,
    UnauthorizedCredentialUseError,
)
from app.vault.domain import Secret, SecretMetadata, SecretVersion
from app.vault.exceptions import VaultException
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.target_accounts.models import TargetAccountBinding

@pytest.fixture
def credential_use_service():
    mock_vault_repo = MagicMock()
    mock_encryption_svc = MagicMock()
    mock_encryption_svc.decrypt_payload.return_value = b"ephemeral-plaintext-password-123"
    svc = CredentialUseService(mock_vault_repo, mock_encryption_svc)
    return svc, mock_vault_repo, mock_encryption_svc

@pytest.fixture
def valid_db_mock():
    with patch("app.vault.credential_use.db") as mock_db:
        yield mock_db

def create_valid_context_and_mocks():
    user_id = uuid4()
    resource_id = uuid4()
    credential_id = uuid4()
    session_id = uuid4()
    grant_id = uuid4()
    binding_id = uuid4()
    req_id = uuid4()
    now = datetime.now(timezone.utc)

    context = CredentialUseContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=credential_id,
        session_id=session_id,
        grant_id=grant_id,
        target_account_binding_id=binding_id,
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    mock_session = MagicMock(spec=PrivilegedAccessSession)
    mock_session.id = session_id
    mock_session.status = SessionStatus.ACTIVE
    mock_session.user_id = user_id
    mock_session.access_request_id = req_id
    mock_session.expires_at = now + timedelta(minutes=15)

    mock_grant = MagicMock(spec=JITAccessGrant)
    mock_grant.id = grant_id
    mock_grant.status = JITGrantStatus.ACTIVE
    mock_grant.user_id = user_id
    mock_grant.approval_request_id = req_id
    mock_grant.expires_at = now + timedelta(minutes=15)

    mock_binding = MagicMock(spec=TargetAccountBinding)
    mock_binding.id = binding_id
    mock_binding.resource_id = resource_id
    mock_binding.ssh_credential_id = credential_id

    mock_secret = MagicMock(spec=Secret)
    mock_secret.id = credential_id
    mock_secret.resource_id = resource_id
    mock_version = MagicMock(spec=SecretVersion)
    mock_version.encrypted_dek = b"enc_dek"
    mock_version.encrypted_payload = b"enc_payload"
    mock_version.metadata = SecretMetadata("v1", "AES", "nonce", {})
    mock_secret.current_version = mock_version

    return context, mock_session, mock_grant, mock_binding, mock_secret

def setup_db_get(mock_db, mock_session, mock_grant, mock_binding):
    def side_effect(model, ident):
        if model == PrivilegedAccessSession and ident == mock_session.id:
            return mock_session
        if model == JITAccessGrant and ident == mock_grant.id:
            return mock_grant
        if model == TargetAccountBinding and ident == mock_binding.id:
            return mock_binding
        return None
    mock_db.session.get.side_effect = side_effect

def test_acquire_ephemeral_credential_success(credential_use_service, valid_db_mock):
    svc, mock_repo, mock_enc = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    mock_repo.find_by_id.return_value = m_sec

    plaintext = svc.acquire_ephemeral_credential(context)
    assert plaintext == b"ephemeral-plaintext-password-123"
    mock_repo.find_by_id.assert_called_once_with(context.credential_id)
    mock_enc.decrypt_payload.assert_called_once()

def test_acquire_ephemeral_credential_missing_deep_validation_ids(credential_use_service):
    svc, _, _ = credential_use_service
    now = datetime.now(timezone.utc)
    
    ctx1 = CredentialUseContext(user_id=uuid4(), resource_id=uuid4(), credential_id=uuid4(), requested_at=now, expires_at=now+timedelta(hours=1))
    with pytest.raises(UnauthorizedCredentialUseError, match="session_id is required"):
        svc.acquire_ephemeral_credential(ctx1)

def test_mismatched_user_id_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_sess.user_id = uuid4() # Wrong user
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    
    with pytest.raises(UnauthorizedCredentialUseError, match="session user does not match context"):
        svc.acquire_ephemeral_credential(context)

def test_terminated_session_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_sess.status = SessionStatus.TERMINATED
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    
    with pytest.raises(UnauthorizedCredentialUseError, match="is not ACTIVE"):
        svc.acquire_ephemeral_credential(context)

def test_revoked_grant_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_grant.status = JITGrantStatus.REVOKED
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    
    with pytest.raises(UnauthorizedCredentialUseError, match="is not ACTIVE"):
        svc.acquire_ephemeral_credential(context)

def test_mismatched_grant_to_session_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_grant.approval_request_id = uuid4() # Mismatched to session's access_request_id
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    
    with pytest.raises(UnauthorizedCredentialUseError, match="grant does not belong to session"):
        svc.acquire_ephemeral_credential(context)

def test_mismatched_target_binding_credential_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_bind.ssh_credential_id = uuid4()
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    
    with pytest.raises(UnauthorizedCredentialUseError, match="target binding credential does not match context"):
        svc.acquire_ephemeral_credential(context)

def test_acquire_ephemeral_credential_unbound_resource_rejected(credential_use_service, valid_db_mock):
    svc, mock_repo, mock_enc = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_sec.resource_id = uuid4() # Secret bound to different resource
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    mock_repo.find_by_id.return_value = m_sec
    
    with pytest.raises(UnauthorizedCredentialUseError, match="is not bound to resource"):
        svc.acquire_ephemeral_credential(context)

    mock_enc.decrypt_payload.assert_not_called()

def test_acquire_ephemeral_credential_expired_context_rejected(credential_use_service):
    svc, mock_repo, mock_enc = credential_use_service
    
    now = datetime.now(timezone.utc)
    context = CredentialUseContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    with pytest.raises(UnauthorizedCredentialUseError, match="has expired"):
        svc.acquire_ephemeral_credential(context)

def test_acquire_ephemeral_credential_secret_not_found(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    mock_repo.find_by_id.return_value = None
    
    with pytest.raises(UnauthorizedCredentialUseError, match="not found"):
        svc.acquire_ephemeral_credential(context)

def test_acquire_ephemeral_credential_missing_version(credential_use_service, valid_db_mock):
    svc, mock_repo, _ = credential_use_service
    context, m_sess, m_grant, m_bind, m_sec = create_valid_context_and_mocks()
    
    m_sec.current_version = None
    setup_db_get(valid_db_mock, m_sess, m_grant, m_bind)
    mock_repo.find_by_id.return_value = m_sec
    
    with pytest.raises(VaultException, match="No active secret version found"):
        svc.acquire_ephemeral_credential(context)

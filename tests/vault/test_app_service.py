import uuid
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest

from app.audit.models import AuditStatus, AuditSeverity
from app.authorization.exceptions import AuthorizationDeniedError
from app.policy_engine.decisions import PolicyDecision
from app.vault.service import VaultApplicationService, ApprovalRequiredError
from app.vault.domain import Secret, SecretVersion, SecretMetadata, SecretStatus


@pytest.fixture
def mock_domain():
    return Mock()


@pytest.fixture
def mock_crypto():
    return Mock()


@pytest.fixture
def mock_repo():
    return Mock()


@pytest.fixture
def mock_policy():
    return Mock()


@pytest.fixture
def mock_audit():
    return Mock()


@pytest.fixture
def mock_authz():
    return Mock()


@pytest.fixture
def mock_session():
    return Mock()


@pytest.fixture
def service(mock_domain, mock_crypto, mock_repo, mock_policy, mock_audit, mock_authz, mock_session):
    return VaultApplicationService(
        domain_service=mock_domain,
        encryption_service=mock_crypto,
        repository=mock_repo,
        policy_engine=mock_policy,
        audit_service=mock_audit,
        authz_service=mock_authz,
        session=mock_session
    )


def test_create_secret_success(service, mock_authz, mock_crypto, mock_repo, mock_audit):
    actor_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    plaintext = b"top-secret"
    
    mock_secret = Mock(spec=Secret)
    mock_secret.id = uuid.uuid4()
    
    with patch("app.vault.service.SecretFactory.create_new_secret", return_value=mock_secret) as mock_factory:
        mock_crypto.encrypt_payload.return_value = (b"enc_dek", b"enc_payload", Mock(spec=SecretMetadata))
        
        result = service.create_secret(actor_id, resource_id, plaintext)
        
        mock_authz.authorize.assert_called_once()
        mock_factory.assert_called_once_with(resource_id)
        mock_repo.save.assert_called_once_with(mock_secret)
        mock_audit.log_event.assert_called_once()
        assert result == mock_secret


def test_retrieve_secret_success_allow(service, mock_authz, mock_policy, mock_repo, mock_crypto, mock_audit):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    
    mock_secret = Mock(spec=Secret)
    type(mock_secret).id = PropertyMock(return_value=secret_id)
    type(mock_secret).resource_id = PropertyMock(return_value=uuid.uuid4())
    mock_version = Mock(spec=SecretVersion)
    mock_version.encrypted_dek = b"enc_dek"
    mock_version.encrypted_payload = b"enc_payload"
    mock_version.metadata = Mock(spec=SecretMetadata)
    mock_secret.get_current_version.return_value = mock_version
    
    mock_repo.find_by_id.return_value = mock_secret
    mock_policy.evaluate_vault_retrieval.return_value = PolicyDecision.ALLOW
    
    mock_crypto.decrypt_payload.return_value = b"decrypted-plaintext"
    
    result = service.retrieve_secret(actor_id, secret_id)
    
    assert result == b"decrypted-plaintext"
    mock_authz.authorize.assert_called_once()
    mock_audit.log_event.assert_called_once_with(
        actor_user_id=actor_id,
        action="SECRET_RETRIEVED",
        resource_type="vault_secrets",
        resource_id=str(secret_id),
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.HIGH,
    )


def test_retrieve_secret_denied_by_rbac(service, mock_authz, mock_repo, mock_audit):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    
    mock_secret = Mock(spec=Secret)
    type(mock_secret).id = PropertyMock(return_value=secret_id)
    type(mock_secret).resource_id = PropertyMock(return_value=uuid.uuid4())
    mock_repo.find_by_id.return_value = mock_secret
    
    mock_authz.authorize.side_effect = AuthorizationDeniedError("No")
    
    with pytest.raises(AuthorizationDeniedError):
        service.retrieve_secret(actor_id, secret_id)
        
    mock_audit.log_event.assert_called_once_with(
        actor_user_id=actor_id,
        action="SECRET_RETRIEVAL_FAILED",
        resource_type="vault_secrets",
        resource_id=str(secret_id),
        status=AuditStatus.DENIED,
        severity=AuditSeverity.HIGH,
        details={"reason": "RBAC Denied"}
    )


def test_retrieve_secret_require_approval(service, mock_authz, mock_policy, mock_repo, mock_audit):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    
    mock_secret = Mock(spec=Secret)
    type(mock_secret).id = PropertyMock(return_value=secret_id)
    type(mock_secret).resource_id = PropertyMock(return_value=uuid.uuid4())
    
    mock_repo.find_by_id.return_value = mock_secret
    mock_policy.evaluate_vault_retrieval.return_value = PolicyDecision.REQUIRE_APPROVAL
    
    with pytest.raises(ApprovalRequiredError):
        service.retrieve_secret(actor_id, secret_id)
        
    mock_audit.log_event.assert_called_once_with(
        actor_user_id=actor_id,
        action="SECRET_RETRIEVAL_FAILED",
        resource_type="vault_secrets",
        resource_id=str(secret_id),
        status=AuditStatus.DENIED,
        severity=AuditSeverity.MEDIUM,
        details={"reason": "Approval Required"}
    )


def test_retrieve_secret_denied_by_policy(service, mock_authz, mock_policy, mock_repo, mock_audit):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    
    mock_secret = Mock(spec=Secret)
    type(mock_secret).id = PropertyMock(return_value=secret_id)
    type(mock_secret).resource_id = PropertyMock(return_value=uuid.uuid4())
    
    mock_repo.find_by_id.return_value = mock_secret
    mock_policy.evaluate_vault_retrieval.return_value = PolicyDecision.DENY
    
    with pytest.raises(AuthorizationDeniedError):
        service.retrieve_secret(actor_id, secret_id)
        
    mock_audit.log_event.assert_called_once_with(
        actor_user_id=actor_id,
        action="SECRET_RETRIEVAL_FAILED",
        resource_type="vault_secrets",
        resource_id=str(secret_id),
        status=AuditStatus.DENIED,
        severity=AuditSeverity.HIGH,
        details={"reason": "Policy Engine Denied"}
    )

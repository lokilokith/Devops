import uuid
from unittest.mock import Mock, PropertyMock

import pytest

from app.vault.models import SecretStatus
from app.vault.service import VaultApplicationService


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
def service(
    mock_domain,
    mock_crypto,
    mock_repo,
    mock_policy,
    mock_audit,
    mock_authz,
    mock_session,
):
    return VaultApplicationService(
        domain_service=mock_domain,
        encryption_service=mock_crypto,
        repository=mock_repo,
        policy_engine=mock_policy,
        audit_service=mock_audit,
        authz_service=mock_authz,
        session=mock_session,
    )


def test_delete_secret_success(service, mock_authz, mock_repo, mock_audit):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()

    mock_secret = Mock()
    type(mock_secret).id = PropertyMock(return_value=secret_id)
    type(mock_secret).resource_id = PropertyMock(return_value=uuid.uuid4())
    type(mock_secret).status = PropertyMock(return_value=SecretStatus.ACTIVE)

    mock_repo.find_by_id.return_value = mock_secret

    service.delete_secret(actor_id, secret_id)

    mock_secret.tombstone.assert_called_once()
    mock_repo.save.assert_called_once_with(mock_secret)
    service._session.commit.assert_called()


def test_delete_secret_not_found(service, mock_repo):
    actor_id = uuid.uuid4()
    secret_id = uuid.uuid4()

    mock_repo.find_by_id.return_value = None

    with pytest.raises(ValueError, match="Secret not found"):
        service.delete_secret(actor_id, secret_id)

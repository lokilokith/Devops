import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.execution.domain import FailureClassification
from app.identity.models import UserStatus
from app.resources.models import ResourceStatus
from app.target_accounts.models import TargetAccountBindingStatus
from app.target_accounts.service import TargetAccountService


def test_provision_target_account_user_not_found():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    svc._user_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="does not exist"):
        svc.provision_target_account(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


def test_provision_target_account_resource_not_found():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    u = MagicMock()
    u.status = UserStatus.ACTIVE
    u.username = "testuser"
    svc._user_repo.get_by_id.return_value = u
    svc._resource_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="does not exist"):
        svc.provision_target_account(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


def test_provision_target_account_binding_suspended():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    u = MagicMock()
    u.status = UserStatus.ACTIVE
    u.username = "testuser"
    r = MagicMock()
    r.status = ResourceStatus.ACTIVE
    svc._user_repo.get_by_id.return_value = u
    svc._resource_repo.get_by_id.return_value = r
    b = MagicMock(status=TargetAccountBindingStatus.SUSPENDED)
    svc._binding_repo.find_by_user_and_resource.return_value = b
    with pytest.raises(ValueError, match="SUSPENDED"):
        svc.provision_target_account(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


def test_provision_target_account_binding_removed():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    u = MagicMock()
    u.status = UserStatus.ACTIVE
    u.username = "testuser"
    r = MagicMock()
    r.status = ResourceStatus.ACTIVE
    svc._user_repo.get_by_id.return_value = u
    svc._resource_repo.get_by_id.return_value = r
    b = MagicMock(status=TargetAccountBindingStatus.REMOVED)
    svc._binding_repo.find_by_user_and_resource.return_value = b
    with pytest.raises(ValueError, match="REMOVED"):
        svc.provision_target_account(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


@patch("app.target_accounts.service.SqlAlchemyVaultRepository")
def test_provision_target_account_execution_failure(mock_vault_repo_cls):
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    u = MagicMock(status=UserStatus.ACTIVE)
    u.username = "testuser"
    r = MagicMock(status=ResourceStatus.ACTIVE)
    svc._user_repo.get_by_id.return_value = u
    svc._resource_repo.get_by_id.return_value = r

    svc._binding_repo.find_by_user_and_resource.return_value = None
    svc._binding_repo.list_bindings_for_resource.return_value = []

    # Mock vault interaction
    mock_vault_repo_instance = MagicMock()
    mock_vault_repo_instance.find_by_resource.return_value = None
    mock_vault_repo_cls.return_value = mock_vault_repo_instance

    svc._encryption_service.encrypt_payload.return_value = (
        b"dek",
        b"payload",
        MagicMock(),
    )

    # Mock executor failure
    exec_result = MagicMock()
    exec_result.success = False
    exec_result.error_message = "Test error"
    exec_result.failure_classification = FailureClassification.UNCERTAIN_STATE

    svc._executor.provision_account.return_value = exec_result

    with pytest.raises(RuntimeError, match="provisioning failed for"):
        svc.provision_target_account(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    # Verify audit event for failure was called
    svc._audit_service.log_event.assert_called()


def test_remove_target_account_not_found():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    svc._binding_repo.find_by_user_and_resource.return_value = None
    with pytest.raises((ValueError, RuntimeError)):
        svc.remove_target_account(uuid.uuid4(), uuid.uuid4())


def test_remove_target_account_already_removed():
    svc = TargetAccountService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    b = MagicMock(status=TargetAccountBindingStatus.REMOVED)
    svc._binding_repo.find_by_user_and_resource.return_value = b
    with pytest.raises((ValueError, RuntimeError)):
        svc.remove_target_account(uuid.uuid4(), uuid.uuid4())

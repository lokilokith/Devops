import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.vault_lifecycle.service import VaultLifecycleService


def test_complete_rotation():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with patch("app.vault.repository.SqlAlchemyVaultRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        secret_mock = MagicMock()
        mock_repo_instance.find_by_id.return_value = secret_mock

        policy_mock = MagicMock()
        policy_mock.rotation_interval_seconds = 3600
        svc._repository.get_by_vault_secret_id.return_value = policy_mock

        svc.complete_rotation(uuid.uuid4(), uuid.uuid4(), MagicMock())

        secret_mock.complete_rotation.assert_called_once()
        mock_repo_instance.save.assert_called_once_with(secret_mock)
        svc._repository.save.assert_called_once_with(policy_mock)


def test_fail_rotation():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with patch("app.vault.repository.SqlAlchemyVaultRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        secret_mock = MagicMock()
        mock_repo_instance.find_by_id.return_value = secret_mock

        policy_mock = MagicMock()
        svc._repository.get_by_vault_secret_id.return_value = policy_mock

        svc.fail_rotation(uuid.uuid4(), uuid.uuid4(), "error")

        secret_mock.fail_rotation.assert_called_once()
        mock_repo_instance.save.assert_called_once_with(secret_mock)
        svc._repository.save.assert_called_once_with(policy_mock)


def test_complete_rotation_secret_not_found():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with patch("app.vault.repository.SqlAlchemyVaultRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.find_by_id.return_value = None
        with pytest.raises(ValueError, match="Secret not found"):
            svc.complete_rotation(uuid.uuid4(), uuid.uuid4(), MagicMock())


def test_fail_rotation_secret_not_found():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with patch("app.vault.repository.SqlAlchemyVaultRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.find_by_id.return_value = None
        with pytest.raises(ValueError, match="Secret not found"):
            svc.fail_rotation(uuid.uuid4(), uuid.uuid4(), "error")

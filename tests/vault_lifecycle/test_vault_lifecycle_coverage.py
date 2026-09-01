import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.vault_lifecycle.models import SecretRotationPolicy
from app.vault_lifecycle.service import (
    AuthorizationDeniedError,
    PolicyNotFoundError,
    PolicyValidationError,
    VaultLifecycleService,
)


def test_create_policy_integrity_error():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._repository.save.side_effect = IntegrityError("error", "params", "orig")
    with pytest.raises(PolicyValidationError):
        svc.create_policy(
            uuid.uuid4(),
            {"vault_secret_id": str(uuid.uuid4()), "rotation_interval_seconds": 3600},
        )


def test_get_policy_not_found():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._repository.find_by_id.return_value = None
    with pytest.raises(PolicyNotFoundError):
        svc.get_policy(uuid.uuid4(), uuid.uuid4())


def test_get_policy_success():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    p = MagicMock()
    svc._repository.find_by_id.return_value = p
    assert svc.get_policy(uuid.uuid4(), uuid.uuid4()) == p


def test_update_policy_authorization_error():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._authz.authorize.side_effect = AuthorizationDeniedError("denied")
    with pytest.raises(AuthorizationDeniedError):
        svc.update_policy(uuid.uuid4(), uuid.uuid4(), {})


def test_update_policy_not_found():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._repository.find_by_id.return_value = None
    with pytest.raises(PolicyNotFoundError):
        svc.update_policy(uuid.uuid4(), uuid.uuid4(), {})


def test_update_policy_success():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    p = SecretRotationPolicy(rotation_interval_seconds=3600)
    p.created_at = datetime.now(timezone.utc)
    svc._repository.find_by_id.return_value = p
    updated = svc.update_policy(
        uuid.uuid4(), uuid.uuid4(), {"rotation_interval_seconds": 7200}
    )
    assert updated.rotation_interval_seconds == 7200


def test_delete_policy_authorization_error():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._authz.authorize.side_effect = AuthorizationDeniedError("denied")
    with pytest.raises(AuthorizationDeniedError):
        svc.delete_policy(uuid.uuid4(), uuid.uuid4())


def test_delete_policy_not_found():
    svc = VaultLifecycleService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    svc._repository.find_by_id.return_value = None
    with pytest.raises(PolicyNotFoundError):
        svc.delete_policy(uuid.uuid4(), uuid.uuid4())

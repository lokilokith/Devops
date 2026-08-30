"""Unit tests for VaultLifecycleService extra domain methods."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault_lifecycle.engine import RotationEligibilityStatus
from app.vault_lifecycle.exceptions import PolicyNotFoundError
from app.vault_lifecycle.service import VaultLifecycleService


def test_delete_policy_rbac_denied():
    session = MagicMock()
    repo = MagicMock()
    authz = MagicMock()
    authz.authorize.side_effect = AuthorizationDeniedError("Denied")
    audit = MagicMock()

    service = VaultLifecycleService(repo, audit, authz, session)
    actor_id = uuid4()
    policy_id = uuid4()

    with pytest.raises(AuthorizationDeniedError):
        service.delete_policy(actor_id, policy_id)

    assert audit.log_event.called is True


def test_delete_policy_not_found():
    session = MagicMock()
    repo = MagicMock()
    repo.find_by_id.return_value = None
    authz = MagicMock()
    audit = MagicMock()

    service = VaultLifecycleService(repo, audit, authz, session)
    actor_id = uuid4()
    policy_id = uuid4()

    with pytest.raises(PolicyNotFoundError):
        service.delete_policy(actor_id, policy_id)


def test_delete_policy_success():
    session = MagicMock()
    repo = MagicMock()
    policy = MagicMock()
    repo.find_by_id.return_value = policy
    authz = MagicMock()
    audit = MagicMock()

    service = VaultLifecycleService(repo, audit, authz, session)
    actor_id = uuid4()
    policy_id = uuid4()

    service.delete_policy(actor_id, policy_id)

    assert repo.delete.called is True
    assert session.commit.called is True
    assert audit.log_event.called is True


def test_evaluate_secret():
    session = MagicMock()
    repo = MagicMock()
    policy = MagicMock()
    policy.is_active = True
    policy.rotation_interval_seconds = 86400
    policy.next_rotation_at = datetime.now(timezone.utc) - timedelta(hours=1)
    repo.get_by_vault_secret_id.return_value = policy
    authz = MagicMock()
    audit = MagicMock()

    service = VaultLifecycleService(repo, audit, authz, session)
    actor_id = uuid4()
    secret_id = uuid4()

    res = service.evaluate_secret(actor_id, secret_id)
    assert res["status"] == RotationEligibilityStatus.DUE
    assert audit.log_event.called is True

"""Tests for Vault Lifecycle Service."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault_lifecycle.exceptions import PolicyNotFoundError, PolicyValidationError
from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus
from app.vault_lifecycle.service import VaultLifecycleService


@pytest.fixture
def lifecycle_repo():
    return Mock()


@pytest.fixture
def audit_service():
    return Mock()


@pytest.fixture
def authz_service():
    return Mock()


@pytest.fixture
def session():
    return Mock()


@pytest.fixture
def service(lifecycle_repo, audit_service, authz_service, session):
    return VaultLifecycleService(lifecycle_repo, audit_service, authz_service, session)


def test_create_policy_success(service, lifecycle_repo, authz_service):
    actor_id = uuid.uuid4()
    vault_secret_id = uuid.uuid4()
    
    lifecycle_repo.get_by_vault_secret_id.return_value = None
    
    data = {
        "vault_secret_id": vault_secret_id,
        "rotation_interval_seconds": 3600
    }
    
    policy = service.create_policy(actor_id, data)
    
    authz_service.authorize.assert_called_once()
    assert policy.vault_secret_id == vault_secret_id
    assert policy.rotation_interval_seconds == 3600
    assert policy.status == RotationStatus.ACTIVE
    lifecycle_repo.save.assert_called_once()


def test_create_policy_authz_denied(service, authz_service):
    actor_id = uuid.uuid4()
    
    authz_service.authorize.side_effect = AuthorizationDeniedError("Denied")
    
    with pytest.raises(AuthorizationDeniedError):
        service.create_policy(actor_id, {"vault_secret_id": uuid.uuid4(), "rotation_interval_seconds": 3600})


def test_create_policy_already_exists(service, lifecycle_repo):
    actor_id = uuid.uuid4()
    vault_secret_id = uuid.uuid4()
    
    lifecycle_repo.get_by_vault_secret_id.return_value = SecretRotationPolicy()
    
    with pytest.raises(PolicyValidationError):
        service.create_policy(actor_id, {"vault_secret_id": vault_secret_id, "rotation_interval_seconds": 3600})


def test_update_policy(service, lifecycle_repo):
    actor_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    
    policy = SecretRotationPolicy(
        id=policy_id,
        rotation_interval_seconds=3600,
        status=RotationStatus.ACTIVE
    )
    lifecycle_repo.find_by_id.return_value = policy
    
    updated = service.update_policy(actor_id, policy_id, {"rotation_interval_seconds": 7200, "status": RotationStatus.PAUSED})
    
    assert updated.rotation_interval_seconds == 7200
    assert updated.status == RotationStatus.PAUSED
    lifecycle_repo.save.assert_called_once()


def test_record_rotation(service, lifecycle_repo):
    vault_secret_id = uuid.uuid4()
    
    policy = SecretRotationPolicy(
        rotation_interval_seconds=3600,
        last_rotated_at=None,
        next_rotation_at=None
    )
    lifecycle_repo.get_by_vault_secret_id.return_value = policy
    
    service.record_rotation(vault_secret_id)
    
    assert policy.last_rotated_at is not None
    assert policy.next_rotation_at is not None
    assert (policy.next_rotation_at - policy.last_rotated_at).total_seconds() == 3600
    lifecycle_repo.save.assert_called_once()

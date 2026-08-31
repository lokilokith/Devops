"""Unit tests for TargetAccountService."""

import uuid

import pytest

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.execution.executor import StubTargetExecutor
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.resources.repository import ResourcesRepository
from app.target_accounts.models import (
    TargetAccountBindingStatus,
)
from app.target_accounts.repository import TargetAccountBindingRepository
from app.target_accounts.service import TargetAccountService
from app.vault.crypto import EncryptionService, LocalKMSProvider
from app.vault.repository import SqlAlchemyVaultRepository


def _setup_service(db_session, executor_mode="success"):
    user = User(
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        username=f"alice_{uuid.uuid4().hex[:6]}",
        email=f"alice_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Alice Engineer",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)

    resource = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name=f"Production Server {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
        hostname_ip="127.0.0.1",
        port=22,
    )
    db_session.add(resource)
    db_session.commit()

    kms = LocalKMSProvider()
    enc = EncryptionService(kms)
    vault_repo = SqlAlchemyVaultRepository(db_session)
    audit_svc = AuditService(AuditRepository(db_session))
    binding_repo = TargetAccountBindingRepository(db_session)
    user_repo = IdentityRepository(db_session)
    res_repo = ResourcesRepository(db_session)

    executor = StubTargetExecutor()
    executor.set_behaviour(resource.id, executor_mode)

    service = TargetAccountService(
        session=db_session,
        binding_repo=binding_repo,
        user_repo=user_repo,
        resource_repo=res_repo,
        audit_service=audit_svc,
        executor=executor,
        encryption_service=enc,
    )

    return service, user, resource, binding_repo, vault_repo, audit_svc


def test_provision_target_account_happy_path(db_session):
    """Test successful lazy target account provisioning."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )

    binding = service.provision_target_account(
        user_id=user.id,
        resource_id=resource.id,
        triggered_by_user_id=user.id,
    )

    assert binding is not None
    assert binding.status == TargetAccountBindingStatus.ACTIVE
    assert binding.control_plane_user_id == user.id
    assert binding.resource_id == resource.id
    assert binding.ssh_credential_id is not None
    assert binding.last_verified_at is not None

    # Verify dedicated Vault secret was created
    secret = vault_repo.find_by_id(binding.ssh_credential_id)
    assert secret is not None


def test_provision_target_account_idempotent(db_session):
    """Test duplicate provisioning returns same ACTIVE binding idempotently."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )

    binding1 = service.provision_target_account(
        user_id=user.id,
        resource_id=resource.id,
        triggered_by_user_id=user.id,
    )

    binding2 = service.provision_target_account(
        user_id=user.id,
        resource_id=resource.id,
        triggered_by_user_id=user.id,
    )

    assert binding1.id == binding2.id
    assert binding2.status == TargetAccountBindingStatus.ACTIVE


def test_provision_target_account_inactive_user_fails_closed(db_session):
    """Test provisioning fails closed when user is inactive."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )
    user.status = UserStatus.SUSPENDED
    db_session.commit()

    with pytest.raises(ValueError, match="cannot provision target account"):
        service.provision_target_account(
            user_id=user.id,
            resource_id=resource.id,
            triggered_by_user_id=user.id,
        )


def test_provision_target_account_inactive_resource_fails_closed(db_session):
    """Test provisioning fails closed when resource is inactive."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )
    resource.status = ResourceStatus.INACTIVE
    db_session.commit()

    with pytest.raises(ValueError, match="cannot provision target account"):
        service.provision_target_account(
            user_id=user.id,
            resource_id=resource.id,
            triggered_by_user_id=user.id,
        )


def test_provision_target_account_zero_plaintext_leakage(db_session):
    """Test zero plaintext private key in audit logs or binding models."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )

    binding = service.provision_target_account(
        user_id=user.id,
        resource_id=resource.id,
        triggered_by_user_id=user.id,
    )
    assert binding is not None

    from sqlalchemy import select

    events = db_session.execute(select(AuditLog)).scalars().all()
    assert len(events) > 0

    for event in events:
        details_str = str(event.details) if event.details else ""
        assert "BEGIN OPENSSH PRIVATE KEY" not in details_str
        assert "PRIVATE KEY" not in details_str


def test_suspend_and_remove_target_account_lifecycle(db_session):
    """Test suspend and remove lifecycle transitions."""
    service, user, resource, binding_repo, vault_repo, audit_svc = _setup_service(
        db_session, executor_mode="success"
    )

    binding = service.provision_target_account(
        user_id=user.id,
        resource_id=resource.id,
        triggered_by_user_id=user.id,
    )

    # 1. Suspend
    suspended = service.suspend_target_account(
        binding_id=binding.id,
        actor_user_id=user.id,
    )
    assert suspended.status == TargetAccountBindingStatus.SUSPENDED

    # 2. Remove
    removed = service.remove_target_account(
        binding_id=binding.id,
        actor_user_id=user.id,
    )
    assert removed.status == TargetAccountBindingStatus.REMOVED

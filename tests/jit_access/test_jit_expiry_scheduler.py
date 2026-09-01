"""Tests for JIT Expiry Enforcement Scheduler and Worker (Phase 7)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.execution.domain import (
    ExecutionOperation,
    ExecutionResult,
    ExecutionStatus,
    VerificationStatus,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository
from app.workers.jit_expiry_worker import JITExpiryWorker
from tests.fixtures.factories import (
    AccessRequestFactory,
    ResourceFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture
def jit_worker_setup(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(requester_id=user.id)
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username="app-user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding)
    db_session.flush()

    from app.access_requests.repository import AccessRequestRepository
    from app.access_requests.service import AccessRequestService
    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.authorization.service import AuthorizationService
    from app.identity.repository import IdentityRepository
    from app.policy_engine.repository import PolicyRepository
    from app.policy_engine.service import PolicyService
    from app.resources.repository import ResourcesRepository
    from app.roles.repository import RolesRepository
    from app.user_roles.repository import UserRolesRepository

    ar_service = AccessRequestService(
        AccessRequestRepository(db_session),
        IdentityRepository(db_session),
        RolesRepository(db_session),
        ResourcesRepository(db_session),
        UserRolesRepository(db_session),
    )
    auth_service = AuthorizationService(db_session)
    audit_service = AuditService(AuditRepository(db_session))
    policy_service = PolicyService(
        PolicyRepository(db_session), auth_service, audit_service
    )
    repo = JITAccessRepository(db_session)
    binding_repo = TargetAccountBindingRepository(db_session)

    service = JITAccessService(
        repository=repo,
        access_request_service=ar_service,
        policy_service=policy_service,
        audit_service=audit_service,
        auth_service=auth_service,
        target_account_repo=binding_repo,
        session=db_session,
    )

    return {
        "user": user,
        "role": role,
        "resource": resource,
        "ar": ar,
        "binding": binding,
        "service": service,
        "repo": repo,
        "audit_service": audit_service,
    }


def test_expiry_worker_discovers_and_expires_grant(jit_worker_setup, db_session):
    """Verify worker discovers expired grants, calls revoke, and records observed overrun."""
    data = jit_worker_setup
    now = datetime.now(timezone.utc)
    past_expiry = now - timedelta(seconds=2)

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=past_expiry,
    )
    db_session.add(grant)
    db_session.commit()

    mock_executor = MagicMock()
    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"terminated_count": 0},
        duration_ms=10.0,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"removed": True},
        duration_ms=15.0,
    )

    worker = JITExpiryWorker(
        service=data["service"],
        audit_service=data["audit_service"],
        executor=mock_executor,
    )

    results = worker.process_expired_grants(now)
    assert len(results) == 1
    assert results[0]["status"] == "expired"
    assert results[0]["slo_breach"] is False

    db_session.refresh(grant)
    assert grant.status == JITGrantStatus.EXPIRED
    assert grant.revocation_start is not None
    assert grant.revocation_complete is not None
    assert grant.observed_overrun_ms is not None
    assert grant.observed_overrun_ms >= 0


def test_expiry_worker_slo_breach_alerting(jit_worker_setup, db_session):
    """Verify worker raises alert when observed overrun exceeds 5s SLO."""
    data = jit_worker_setup
    now = datetime.now(timezone.utc)
    ancient_expiry = now - timedelta(seconds=12)  # 12s in past

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=ancient_expiry,
    )
    db_session.add(grant)
    db_session.commit()

    mock_executor = MagicMock()
    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"terminated_count": 0},
        duration_ms=10.0,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"removed": True},
        duration_ms=10.0,
    )

    worker = JITExpiryWorker(
        service=data["service"],
        audit_service=data["audit_service"],
        executor=mock_executor,
        max_overrun_slo_ms=5000,
    )

    results = worker.process_expired_grants(now)
    assert len(results) == 1
    assert results[0]["slo_breach"] is True
    assert results[0]["observed_overrun_ms"] >= 10000


def test_worker_down_scenario_and_startup_recovery(jit_worker_setup, db_session):
    """Simulate worker-down scenario: grant expires while worker is stopped.

    Upon worker restart, run_recovery_on_startup immediately catches the backlogged
    expired grant, revokes target-side privilege, and records the measured overrun.
    """
    data = jit_worker_setup
    now = datetime.now(timezone.utc)
    grant_expired_during_downtime = now - timedelta(minutes=5)

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="nginx_reload",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=grant_expired_during_downtime,
    )
    db_session.add(grant)
    db_session.commit()

    mock_executor = MagicMock()
    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"terminated_count": 0},
        duration_ms=10.0,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"removed": True},
        duration_ms=10.0,
    )

    # Worker starts up
    worker = JITExpiryWorker(
        service=data["service"],
        audit_service=data["audit_service"],
        executor=mock_executor,
    )
    recovery_results = worker.run_recovery_on_startup()

    assert len(recovery_results) == 1
    assert recovery_results[0]["status"] == "expired"
    assert recovery_results[0]["observed_overrun_ms"] >= 300000  # >= 5 minutes

    db_session.refresh(grant)
    assert grant.status == JITGrantStatus.EXPIRED

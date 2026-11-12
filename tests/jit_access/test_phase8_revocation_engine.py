"""Unit tests for Phase 8 JIT Revocation Engine.

Covers:
- Revocation state machine (ACTIVE -> REVOCATION_RUNNING -> REVOKED/EXPIRED)
- Concurrency & CAS optimistic locking
- Worker leasing and fencing
- Security uncertainty fail-closed handling
- Crash recovery of interrupted revocations
- Anti-resurrection invariant enforcement
- Zero secret leakage
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.executor import StubTargetExecutor
from app.jit_access.exceptions import (
    InvalidGrantStateError,
    JITAccessError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.revocation_engine import JITRevocationEngine
from app.resources.models import Environment, ResourceStatus, ResourceType
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus


@pytest.fixture
def mock_audit():
    audit = MagicMock(spec=AuditService)
    return audit


@pytest.fixture
def test_grant(db_session):
    now = datetime.now(timezone.utc)
    from app.access_requests.models import (
        AccessRequest,
        AccessRequestPriority,
        AccessRequestStatus,
    )
    from app.identity.models import User, UserStatus
    from app.resources.models import Resource
    from app.roles.models import Role

    user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"jit_user_{uuid4().hex[:8]}@example.com",
        username=f"u_{uuid4().hex[:8]}",
        full_name="JIT User",
        password_hash="hashed_pw",
        status=UserStatus.ACTIVE,
    )
    role = Role(
        role_code=f"P8_ROLE_{uuid4().hex[:6].upper()}",
        role_name=f"P8 Role {uuid4().hex[:6]}",
        description="test role",
    )
    resource = Resource(
        resource_code=f"RES_{uuid4().hex[:6].upper()}",
        resource_name=f"Target Server {uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
    )
    db_session.add_all([user, role, resource])
    db_session.flush()  # resolve IDs before FK references

    ar = AccessRequest(
        requester_id=user.id,
        requested_role_id=role.id,
        request_number=f"REQ-P8-{uuid4().hex[:8].upper()}",
        business_justification="JIT testing",
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
    )
    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username=f"u_{user.username[:10]}",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add_all([ar, binding])
    db_session.commit()

    grant = JITAccessGrant(
        id=uuid4(),
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        approval_request_id=ar.id,
        command_set_id="system_health_check",
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(hours=1),
        row_version=1,
    )
    db_session.add(grant)
    db_session.commit()
    return grant


def test_revocation_engine_successful_manual_revocation(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    revoked_grant = engine.revoke_grant(
        grant_id=test_grant.id,
        actor_id=test_grant.user_id,
        is_expiry=False,
        executor=executor,
        worker_id="worker_test_1",
    )

    assert revoked_grant.status == JITGrantStatus.REVOKED
    assert revoked_grant.revoked_at is not None
    assert revoked_grant.revocation_complete is not None
    assert revoked_grant.row_version >= 2

    # Audit events verified — engine emits revocation_started then revoked
    mock_audit.log_event.assert_any_call(
        actor_user_id=test_grant.user_id,
        action="jit_grant.revocation_started",
        resource_type="jit_access_grants",
        resource_id=str(test_grant.id),
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.INFO,
        details={
            "worker_id": "worker_test_1",
            "is_expiry": False,
            "target_account_binding_id": str(test_grant.target_account_binding_id),
        },
    )


def test_revocation_engine_successful_expiry_revocation(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    # Set expires_at in past
    test_grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    repo.save(test_grant)

    expired_grant = engine.revoke_grant(
        grant_id=test_grant.id,
        actor_id=test_grant.user_id,
        is_expiry=True,
        executor=executor,
        worker_id="expiry_worker_1",
    )

    assert expired_grant.status == JITGrantStatus.EXPIRED
    assert expired_grant.observed_overrun_ms is not None
    assert expired_grant.observed_overrun_ms >= 0


def test_revocation_engine_idempotency_on_terminal_state(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    revoked1 = engine.revoke_grant(
        test_grant.id, test_grant.user_id, is_expiry=False, executor=executor
    )
    assert revoked1.status == JITGrantStatus.REVOKED

    # Repeated revocation returns already revoked state cleanly
    revoked2 = engine.revoke_grant(
        test_grant.id, test_grant.user_id, is_expiry=False, executor=executor
    )
    assert revoked2.status == JITGrantStatus.REVOKED


def test_revocation_engine_worker_fencing_rejection(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    now = datetime.now(timezone.utc)
    # Worker 1 claims with active lease
    test_grant.status = JITGrantStatus.REVOCATION_RUNNING
    test_grant.revocation_worker_id = "worker_1"
    test_grant.revocation_lease_expires_at = now + timedelta(minutes=5)
    repo.save(test_grant)

    # Worker 2 attempts claim while Worker 1 lease is valid
    with pytest.raises(InvalidGrantStateError, match="could not be claimed"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=executor,
            worker_id="worker_2",
        )


def test_revocation_engine_security_uncertainty_handling(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    # Configure stub executor to fail with uncertain state
    executor = StubTargetExecutor(default_mode="uncertain_state")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="security uncertainty"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=executor,
            worker_id="worker_1",
        )

    refreshed = repo.get_by_id(test_grant.id)
    assert refreshed.status == JITGrantStatus.SECURITY_UNCERTAIN
    assert refreshed.failure_reason is not None


def test_revocation_engine_crash_recovery_of_interrupted_grants(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    # Simulate crashed worker: status is REVOCATION_RUNNING with expired lease in past
    now = datetime.now(timezone.utc)
    test_grant.status = JITGrantStatus.REVOCATION_RUNNING
    test_grant.revocation_worker_id = "crashed_worker"
    test_grant.revocation_lease_expires_at = now - timedelta(seconds=10)
    repo.save(test_grant)

    results = engine.recover_interrupted_revocations(
        executor=executor, worker_id="recovery_daemon"
    )
    assert len(results) == 1
    assert results[0]["recovered"] is True

    refreshed = repo.get_by_id(test_grant.id)
    assert refreshed.status in (JITGrantStatus.REVOKED, JITGrantStatus.EXPIRED)


def test_no_privilege_resurrection_on_revoked_grant(db_session, test_grant, mock_audit):
    from app.access_requests.service import AccessRequestService
    from app.authorization.service import AuthorizationService
    from app.jit_access.service import JITAccessService
    from app.policy_engine.service import PolicyService

    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    # First revoke grant
    engine.revoke_grant(test_grant.id, test_grant.user_id, executor=executor)
    assert repo.get_by_id(test_grant.id).status == JITGrantStatus.REVOKED

    # Attempt to reactivate revoked grant
    ar_service = MagicMock(spec=AccessRequestService)
    auth_service = MagicMock(spec=AuthorizationService)
    auth_service.has_permission.return_value = True
    policy_service = MagicMock(spec=PolicyService)

    svc = JITAccessService(
        repository=repo,
        access_request_service=ar_service,
        policy_service=policy_service,
        audit_service=mock_audit,
        auth_service=auth_service,
        session=db_session,
    )

    with pytest.raises(
        InvalidGrantStateError, match="Only pending grants can be activated"
    ):
        svc.activate_grant(test_grant.id, test_grant.user_id, executor=executor)


def test_zero_plaintext_leakage_in_audit_and_exceptions(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="success")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    # Execute revocation
    engine.revoke_grant(test_grant.id, test_grant.user_id, executor=executor)

    # Inspect all audit calls
    for call in mock_audit.log_event.call_args_list:
        kwargs = call[1]
        details_str = str(kwargs.get("details", {}))
        assert "password" not in details_str.lower()
        assert "private_key" not in details_str.lower()
        assert "BEGIN OPENSSH PRIVATE KEY" not in details_str


def test_revocation_engine_revoke_jit_grant_uncertainty(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)

    class CustomStubExecutor(StubTargetExecutor):
        def revoke_jit_grant(self, request):
            from app.execution.domain import (
                ExecutionOperation,
                ExecutionResult,
                ExecutionStatus,
                FailureClassification,
                VerificationStatus,
            )

            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.UNCERTAIN_STATE,
                error_message="Revoke uncertain",
            )

    custom_executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(
        JITAccessError, match="Sudoers privilege revocation failed: Revoke uncertain"
    ):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=custom_executor,
            worker_id="worker_1",
        )


def test_revocation_engine_revoke_jit_grant_failure(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)

    class CustomStubExecutor(StubTargetExecutor):
        def revoke_jit_grant(self, request):
            from app.execution.domain import (
                ExecutionOperation,
                ExecutionResult,
                ExecutionStatus,
                FailureClassification,
                VerificationStatus,
            )

            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message="Revoke failed completely",
            )

    custom_executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="Revoke failed completely"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=custom_executor,
            worker_id="worker_1",
        )


def test_revocation_engine_session_termination_failure(
    db_session, test_grant, mock_audit
):
    repo = JITAccessRepository(db_session)

    class CustomStubExecutor(StubTargetExecutor):
        def terminate_jit_sessions(self, request):
            from app.execution.domain import (
                ExecutionOperation,
                ExecutionResult,
                ExecutionStatus,
                FailureClassification,
                VerificationStatus,
            )

            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message="Term failed completely",
            )

    executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(
        JITAccessError, match="Failed to terminate JIT sessions: Term failed completely"
    ):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=executor,
            worker_id="worker_1",
        )

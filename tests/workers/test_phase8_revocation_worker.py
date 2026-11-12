"""Unit tests for Phase 8 JIT Revocation Worker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.audit.service import AuditService
from app.execution.executor import StubTargetExecutor
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.workers.jit_expiry_worker import JITExpiryWorker
from app.workers.jit_revocation_worker import JITRevocationWorker


@pytest.fixture
def mock_audit():
    return MagicMock(spec=AuditService)


@pytest.fixture
def test_grants(db_session):
    now = datetime.now(timezone.utc)
    from app.access_requests.models import (
        AccessRequest,
        AccessRequestPriority,
        AccessRequestStatus,
    )
    from app.identity.models import User, UserStatus
    from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
    from app.roles.models import Role
    from app.target_accounts.models import (
        TargetAccountBinding,
        TargetAccountBindingStatus,
    )

    user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"worker_user_{uuid4().hex[:8]}@example.com",
        username=f"u_{uuid4().hex[:8]}",
        full_name="Worker User",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    role = Role(
        role_code=f"P8_ROLE_{uuid4().hex[:6].upper()}",
        role_name=f"P8 Role {uuid4().hex[:6]}",
        description="test",
    )
    resource = Resource(
        resource_code=f"RES_{uuid4().hex[:6].upper()}",
        resource_name=f"Server {uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
    )
    db_session.add_all([user, role, resource])
    db_session.flush()  # resolve IDs before FK references

    ar1 = AccessRequest(
        requester_id=user.id,
        requested_role_id=role.id,
        request_number=f"REQ-P8-{uuid4().hex[:8].upper()}",
        business_justification="req 1",
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
    )
    ar2 = AccessRequest(
        requester_id=user.id,
        requested_role_id=role.id,
        request_number=f"REQ-P8-{uuid4().hex[:8].upper()}",
        business_justification="req 2",
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
    )
    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username=f"u_{user.username[:10]}",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add_all([ar1, ar2, binding])
    db_session.flush()

    # Grant 1: Expired
    grant_expired = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        approval_request_id=ar1.id,
        command_set_id="system_health_check",
        status=JITGrantStatus.ACTIVE,
        expires_at=now - timedelta(seconds=10),
        row_version=1,
    )

    # Grant 2: Interrupted / Abandoned
    grant_interrupted = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        approval_request_id=ar2.id,
        command_set_id="system_health_check",
        status=JITGrantStatus.REVOCATION_RUNNING,
        revocation_worker_id="old_worker",
        revocation_lease_expires_at=now - timedelta(seconds=5),
        expires_at=now - timedelta(seconds=20),
        row_version=1,
    )

    db_session.add_all([grant_expired, grant_interrupted])
    db_session.commit()
    return {"expired": grant_expired, "interrupted": grant_interrupted, "user": user}


def test_revocation_worker_processes_expired_and_interrupted(
    db_session, test_grants, mock_audit
):
    from app.access_requests.service import AccessRequestService
    from app.authorization.service import AuthorizationService
    from app.policy_engine.service import PolicyService

    repo = JITAccessRepository(db_session)
    mock_auth = MagicMock(spec=AuthorizationService)
    mock_ar = MagicMock(spec=AccessRequestService)
    mock_policy = MagicMock(spec=PolicyService)

    svc = JITAccessService(
        repository=repo,
        access_request_service=mock_ar,
        policy_service=mock_policy,
        audit_service=mock_audit,
        auth_service=mock_auth,
        session=db_session,
    )
    executor = StubTargetExecutor(default_mode="success")

    worker = JITRevocationWorker(
        service=svc,
        audit_service=mock_audit,
        executor=executor,
        worker_id="test_worker_8",
    )

    results = worker.run_recovery_on_startup()
    assert len(results) >= 2

    # Verify both grants reached terminal EXPIRED/REVOKED status
    g1 = repo.get_by_id(test_grants["expired"].id)
    g2 = repo.get_by_id(test_grants["interrupted"].id)

    assert g1.status == JITGrantStatus.EXPIRED
    assert g2.status in (JITGrantStatus.EXPIRED, JITGrantStatus.REVOKED)


def test_revocation_worker_slo_breach_detection(db_session, test_grants, mock_audit):
    from app.access_requests.service import AccessRequestService
    from app.authorization.service import AuthorizationService
    from app.policy_engine.service import PolicyService

    repo = JITAccessRepository(db_session)
    mock_auth = MagicMock(spec=AuthorizationService)
    mock_ar = MagicMock(spec=AccessRequestService)
    mock_policy = MagicMock(spec=PolicyService)

    svc = JITAccessService(
        repository=repo,
        access_request_service=mock_ar,
        policy_service=mock_policy,
        audit_service=mock_audit,
        auth_service=mock_auth,
        session=db_session,
    )
    executor = StubTargetExecutor(default_mode="success")

    # Set very small max_overrun_slo_ms to trigger SLO breach
    worker = JITExpiryWorker(
        service=svc,
        audit_service=mock_audit,
        executor=executor,
        max_overrun_slo_ms=1,  # 1ms SLO
        worker_id="slo_tester",
    )

    results = worker.process_expired_grants()
    assert len(results) >= 1
    assert any(r.get("slo_breach") is True for r in results)

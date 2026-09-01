"""Ownership and IDOR authorization tests for Phase 8 JIT Revocation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.access_requests.models import (
    AccessRequest,
    AccessRequestPriority,
    AccessRequestStatus,
)
from app.access_requests.service import AccessRequestService
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.execution.executor import StubTargetExecutor
from app.identity.models import User
from app.jit_access.exceptions import UnauthorizedActivationError
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.policy_engine.service import PolicyService
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.roles.models import Role
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus


@pytest.fixture
def jit_env(db_session):
    now = datetime.now(timezone.utc)
    from app.identity.models import UserStatus

    user_a = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"usera_{uuid4().hex[:8]}@example.com",
        username=f"usera_{uuid4().hex[:8]}",
        full_name="User A",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    user_b = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"userb_{uuid4().hex[:8]}@example.com",
        username=f"userb_{uuid4().hex[:8]}",
        full_name="User B",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    admin_user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"admin_{uuid4().hex[:8]}@example.com",
        username=f"admin_{uuid4().hex[:8]}",
        full_name="Admin User",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    role = Role(
        role_code=f"P8_ROLE_{uuid4().hex[:6].upper()}",
        role_name=f"P8 Role {uuid4().hex[:6]}",
        description="test",
    )
    res = Resource(
        resource_code=f"RES_{uuid4().hex[:6].upper()}",
        resource_name=f"Server {uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
    )
    db_session.add_all([user_a, user_b, admin_user, role, res])
    db_session.flush()  # resolve IDs before FK references

    ar_a = AccessRequest(
        requester_id=user_a.id,
        requested_role_id=role.id,
        request_number=f"REQ-P8-{uuid4().hex[:8].upper()}",
        business_justification="Access for user A",
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
    )
    binding_a = TargetAccountBinding(
        control_plane_user_id=user_a.id,
        resource_id=res.id,
        target_os_username=f"u_{user_a.username[:10]}",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add_all([ar_a, binding_a])
    db_session.flush()

    grant_a = JITAccessGrant(
        user_id=user_a.id,
        role_id=role.id,
        resource_id=res.id,
        target_account_binding_id=binding_a.id,
        approval_request_id=ar_a.id,
        command_set_id="system_health_check",
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(hours=1),
        row_version=1,
    )
    db_session.add(grant_a)
    db_session.commit()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "admin_user": admin_user,
        "grant_a": grant_a,
        "binding_a": binding_a,
        "resource": res,
    }


def test_user_b_cannot_revoke_user_a_grant(db_session, jit_env):
    repo = JITAccessRepository(db_session)
    mock_audit = MagicMock(spec=AuditService)
    mock_auth = MagicMock(spec=AuthorizationService)
    # User B does not have admin permissions
    mock_auth.has_permission.return_value = False
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

    with pytest.raises(
        UnauthorizedActivationError, match="cannot revoke another user's grant"
    ):
        svc.revoke_access(
            grant_id=jit_env["grant_a"].id,
            revoker_id=jit_env["user_b"].id,
            executor=executor,
        )


def test_admin_can_revoke_user_a_grant(db_session, jit_env):
    repo = JITAccessRepository(db_session)
    mock_audit = MagicMock(spec=AuditService)
    mock_auth = MagicMock(spec=AuthorizationService)
    # Admin has delete permission on jit_grants
    mock_auth.has_permission.return_value = True
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

    revoked = svc.revoke_access(
        grant_id=jit_env["grant_a"].id,
        revoker_id=jit_env["admin_user"].id,
        executor=executor,
    )
    assert revoked.status == JITGrantStatus.REVOKED


def test_user_b_cannot_terminate_user_a_session(db_session, jit_env):
    repo = JITAccessRepository(db_session)
    mock_audit = MagicMock(spec=AuditService)
    mock_auth = MagicMock(spec=AuthorizationService)
    mock_auth.has_permission.return_value = False
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

    with pytest.raises(UnauthorizedActivationError, match="cannot terminate sessions"):
        svc.terminate_active_sessions(
            grant_id=jit_env["grant_a"].id,
            user_id=jit_env["user_b"].id,
            executor=executor,
        )


def test_user_b_cannot_register_session_for_user_a(db_session, jit_env):
    repo = JITAccessRepository(db_session)
    mock_audit = MagicMock(spec=AuditService)
    mock_auth = MagicMock(spec=AuthorizationService)
    mock_auth.has_permission.return_value = False
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

    with pytest.raises(UnauthorizedActivationError, match="cannot register sessions"):
        svc.register_active_session(
            grant_id=jit_env["grant_a"].id,
            user_id=jit_env["user_b"].id,
            session_id=uuid4(),
            target_session_pid=12345,
            executor=executor,
        )

"""Additional tests to maximize coverage for Phase 7 JIT access services, routes, worker, and repo."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.access_requests.models import AccessRequestStatus
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.service import AccessRequestService
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.execution.domain import (
    ExecutionOperation,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.identity.repository import IdentityRepository
from app.jit_access.exceptions import (
    GrantNotFoundError,
    InvalidGrantStateError,
    JITAccessError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.policy_engine.repository import PolicyRepository
from app.policy_engine.service import PolicyService
from app.resources.repository import ResourcesRepository
from app.role_permissions.models import RolePermission
from app.roles.models import Role, UserRole
from app.roles.repository import RolesRepository
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository
from app.user_roles.repository import UserRolesRepository
from app.workers.jit_expiry_worker import JITExpiryWorker, run_jit_expiry_job
from tests.fixtures.factories import (
    AccessRequestFactory,
    ResourceFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture(autouse=True)
def setup_permissions(db_session, admin_user):
    ur = db_session.query(UserRole).filter_by(user_id=admin_user.id).first()
    if ur:
        role_id = ur.role_id
    else:
        role = Role(role_code="TEST_ADMIN", role_name="Test Admin")
        db_session.add(role)
        db_session.flush()
        db_session.add(UserRole(user_id=admin_user.id, role_id=role.id))
        db_session.flush()
        role_id = role.id

    for action in [
        PermissionAction.CREATE,
        PermissionAction.READ,
        PermissionAction.UPDATE,
        PermissionAction.DELETE,
    ]:
        perm_code = f"PERM_JIT_GRANTS_{action.value.upper()}"
        perm = (
            db_session.query(Permission)
            .filter_by(permission_code=perm_code, action=action)
            .first()
        )
        if not perm:
            perm = Permission(
                permission_code=perm_code,
                permission_name=f"JIT Grants {action.value.capitalize()}",
                action=action,
                status=PermissionStatus.ACTIVE,
            )
            db_session.add(perm)
            db_session.flush()
        db_session.add(RolePermission(role_id=role_id, permission_id=perm.id))
    db_session.commit()


@pytest.fixture
def jit_coverage_setup(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(requester_id=user.id, status=AccessRequestStatus.APPROVED)
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username="cov-user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding)
    db_session.flush()

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


def test_service_grant_lifecycle_and_queries(
    jit_coverage_setup, db_session, admin_user
):
    data = jit_coverage_setup
    svc = data["service"]

    svc._policy_service.evaluate_policy = lambda **kwargs: {
        "decision": "ALLOW",
        "max_duration_seconds": 7200,
    }

    # 1. Request access
    grant = svc.request_access(
        requester_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        duration_minutes=45,
        reason="Coverage test",
        command_set_id="system_health_check",
    )
    assert grant.status == JITGrantStatus.PENDING

    # 2. Get grant by ID
    fetched = svc.get_grant(grant.id)
    assert fetched.id == grant.id

    # 3. Not found handling
    with pytest.raises(GrantNotFoundError):
        svc.get_grant(uuid.uuid4())

    with pytest.raises(GrantNotFoundError):
        svc.activate_grant(uuid.uuid4(), admin_user.id)

    # 4. Activate grant
    grant.approval_request_id = data["ar"].id
    db_session.flush()

    mock_executor = MagicMock()
    mock_executor.apply_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"verified": True},
        duration_ms=10.0,
    )
    activated = svc.activate_grant(grant.id, admin_user.id, executor=mock_executor)
    assert activated.status == JITGrantStatus.ACTIVE

    # 5. Query active grants
    active_list = svc.get_user_active_grants(data["user"].id)
    assert len(active_list) >= 1

    # 6. List grants with various filters
    res_list, total = svc.list_grants(
        user_id=data["user"].id,
        resource_id=data["resource"].id,
        status=JITGrantStatus.ACTIVE,
        page=1,
        page_size=10,
    )
    assert total >= 1
    assert len(res_list) >= 1

    # 7. Check active grant repository query
    assert data["repo"].check_active_grant(
        data["user"].id, data["role"].id, data["resource"].id
    )

    # 8. Check binding active grant lookup
    binding_grants = data["repo"].find_active_by_binding(data["binding"].id)
    assert len(binding_grants) >= 1

    # 9. Inactive transitions
    grant.status = JITGrantStatus.EXPIRED
    db_session.flush()
    with pytest.raises(InvalidGrantStateError):
        svc.activate_grant(grant.id, admin_user.id)


def test_service_expire_access_edge_cases(jit_coverage_setup, db_session):
    data = jit_coverage_setup
    svc = data["service"]

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(grant)
    db_session.commit()

    # Expire with executor failure
    mock_executor = MagicMock()
    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.FAILED,
        verification_status=VerificationStatus.UNVERIFIED,
        failure_classification=FailureClassification.UNCERTAIN_STATE,
        error_message="SSH target unreachable during revocation",
        duration_ms=10.0,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.FAILED,
        verification_status=VerificationStatus.UNVERIFIED,
        failure_classification=FailureClassification.UNCERTAIN_STATE,
        error_message="SSH target unreachable during revocation",
        duration_ms=10.0,
    )

    with pytest.raises(
        JITAccessError, match="Session termination failed in security uncertainty"
    ):
        svc.expire_access(grant.id, executor=mock_executor)

    db_session.refresh(grant)
    assert grant.status == JITGrantStatus.SECURITY_UNCERTAIN


def test_routes_coverage(client, admin_token, admin_user, db_session):
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(
        status=AccessRequestStatus.APPROVED, requester_id=admin_user.id
    )
    binding = TargetAccountBinding(
        control_plane_user_id=admin_user.id,
        resource_id=resource.id,
        target_os_username="admin-user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add_all([role, resource, ar, binding])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=admin_user.id,
        role_id=role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        command_set_id="system_health_check",
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    # 1. GET /jit/<grant_id>
    resp = client.get(
        f"/jit/{grant.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json["id"] == str(grant.id)

    # 2. GET /jit/non-existent
    resp_404 = client.get(
        f"/jit/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_404.status_code == 404

    # 3. GET /jit/session/current
    resp_sess = client.get(
        "/jit/session/current",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_sess.status_code == 200
    assert len(resp_sess.json) >= 1

    # 4. POST /jit/<grant_id>/revoke
    resp_rev = client.post(
        f"/jit/{grant.id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_rev.status_code == 200
    assert resp_rev.json["status"] == "revoked"


def test_run_jit_expiry_job_invocation(app, jit_coverage_setup, db_session):
    """Test background runner invocation."""
    data = jit_coverage_setup
    now = datetime.now(timezone.utc)
    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=now - timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    due = data["service"]._repo.find_due_expired_grants(now)
    assert len(due) == 1

    mock_exec = MagicMock()
    mock_exec.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"terminated_count": 0},
        duration_ms=10.0,
    )
    mock_exec.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"removed": True},
        duration_ms=10.0,
    )

    worker = JITExpiryWorker(service=data["service"], executor=mock_exec)
    processed = worker.process_expired_grants(now)
    assert len(processed) == 1

    res = run_jit_expiry_job(service=data["service"], executor=mock_exec)
    assert "timestamp" in res


def test_service_validation_errors_and_check_expire(jit_coverage_setup, db_session):
    data = jit_coverage_setup
    svc = data["service"]

    # 1. Invalid command_set_id
    with pytest.raises(JITAccessError, match="Invalid or unallowlisted command_set_id"):
        svc.request_access(
            requester_id=data["user"].id,
            role_id=data["role"].id,
            resource_id=data["resource"].id,
            duration_minutes=30,
            reason="testing",
            command_set_id="ALL_SUDO_COMMANDS",
        )

    # 2. Inactive binding status
    data["binding"].status = TargetAccountBindingStatus.SUSPENDED
    db_session.flush()
    with pytest.raises(JITAccessError, match="not ACTIVE"):
        svc.request_access(
            requester_id=data["user"].id,
            role_id=data["role"].id,
            resource_id=data["resource"].id,
            duration_minutes=30,
            reason="testing",
            command_set_id="system_health_check",
        )
    data["binding"].status = TargetAccountBindingStatus.ACTIVE
    db_session.flush()

    # 3. check_and_expire helper
    now = datetime.now(timezone.utc)
    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.ACTIVE,
        expires_at=now - timedelta(minutes=10),
    )
    db_session.add(grant)
    db_session.commit()

    mock_exec = MagicMock()
    mock_exec.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"terminated_count": 0},
        duration_ms=10.0,
    )
    mock_exec.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={"removed": True},
        duration_ms=10.0,
    )

    expired_count = svc.check_and_expire(executor=mock_exec)
    assert expired_count >= 1

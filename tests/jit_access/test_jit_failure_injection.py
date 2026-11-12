"""Failure injection and security uncertainty tests for Phase 7 JIT."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.execution.domain import (
    ExecutionOperation,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.jit_access.exceptions import JITAccessError
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository
from tests.fixtures.factories import (
    AccessRequestFactory,
    ResourceFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture(autouse=True)
def setup_permissions(db_session, admin_user):
    from app.permissions.models import Permission, PermissionAction, PermissionStatus
    from app.role_permissions.models import RolePermission
    from app.roles.models import Role, UserRole

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
def failure_test_setup(db_session):
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


def test_target_verification_failure_causes_security_uncertainty(
    failure_test_setup, db_session, admin_user
):
    """Case E: SSH/verification failure after mutation transitions grant to SECURITY_UNCERTAIN."""
    data = failure_test_setup
    now = datetime.now(timezone.utc)
    data["ar"].status = data["ar"].status.__class__.APPROVED
    db_session.flush()

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.PENDING,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    mock_executor = MagicMock()
    mock_executor.apply_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        status=ExecutionStatus.FAILED,
        verification_status=VerificationStatus.VERIFIED_FAILURE,
        failure_classification=FailureClassification.UNCERTAIN_STATE,
        error_message="SSH connection lost during independent live sudo verification",
        duration_ms=45.0,
    )

    with pytest.raises(JITAccessError, match="security uncertainty"):
        data["service"].activate_grant(
            grant.id,
            admin_user.id,
            executor=mock_executor,
        )

    db_session.refresh(grant)
    assert grant.status == JITGrantStatus.SECURITY_UNCERTAIN
    assert grant.failure_reason is not None


def test_visudo_rejection_causes_grant_failed_state(
    failure_test_setup, db_session, admin_user
):
    """Case A: Invalid sudoers syntax rejected by visudo transitions grant to FAILED."""
    data = failure_test_setup
    now = datetime.now(timezone.utc)
    data["ar"].status = data["ar"].status.__class__.APPROVED
    db_session.flush()

    grant = JITAccessGrant(
        user_id=data["user"].id,
        role_id=data["role"].id,
        resource_id=data["resource"].id,
        target_account_binding_id=data["binding"].id,
        command_set_id="system_health_check",
        approval_request_id=data["ar"].id,
        status=JITGrantStatus.PENDING,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    mock_executor = MagicMock()
    mock_executor.apply_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        status=ExecutionStatus.FAILED,
        verification_status=VerificationStatus.UNVERIFIED,
        failure_classification=FailureClassification.TARGET_FAILURE,
        error_message="visudo validation failed: syntax error near unexpected token",
        duration_ms=20.0,
    )

    with pytest.raises(JITAccessError, match="JIT grant activation failed"):
        data["service"].activate_grant(
            grant.id,
            admin_user.id,
            executor=mock_executor,
        )

    db_session.refresh(grant)
    assert grant.status == JITGrantStatus.FAILED
    assert "visudo" in (grant.failure_reason or "").lower()

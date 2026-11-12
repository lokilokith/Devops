"""Ownership and IDOR protection tests for Phase 7 JIT."""

from datetime import datetime, timedelta, timezone

import pytest

from app.access_requests.repository import AccessRequestRepository
from app.access_requests.service import AccessRequestService
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.identity.repository import IdentityRepository
from app.jit_access.exceptions import JITAccessError, UnauthorizedActivationError
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.service import JITAccessService
from app.policy_engine.repository import PolicyRepository
from app.policy_engine.service import PolicyService
from app.resources.repository import ResourcesRepository
from app.roles.repository import RolesRepository
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository
from app.user_roles.repository import UserRolesRepository
from tests.fixtures.factories import (
    AccessRequestFactory,
    ResourceFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture
def ownership_setup(db_session):
    user_a = UserFactory()
    user_b = UserFactory()
    role = RoleFactory()
    resource_1 = ResourceFactory()
    resource_2 = ResourceFactory()
    db_session.add_all([user_a, user_b, role, resource_1, resource_2])
    db_session.flush()

    binding_a = TargetAccountBinding(
        control_plane_user_id=user_a.id,
        resource_id=resource_1.id,
        target_os_username="user-a",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding_a)
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
        "user_a": user_a,
        "user_b": user_b,
        "role": role,
        "resource_1": resource_1,
        "resource_2": resource_2,
        "binding_a": binding_a,
        "service": service,
        "repo": repo,
    }


def test_user_b_cannot_request_jit_on_unowned_resource_binding(ownership_setup):
    """User B has no target binding on Resource 1; request must be rejected."""
    data = ownership_setup
    with pytest.raises(JITAccessError, match="User has no target account on resource"):
        data["service"].request_access(
            requester_id=data["user_b"].id,
            role_id=data["role"].id,
            resource_id=data["resource_1"].id,
            duration_minutes=30,
            reason="Attempting unauthorized access",
        )


def test_user_b_cannot_activate_user_a_grant(ownership_setup, db_session):
    """Non-admin User B cannot activate User A's grant."""
    data = ownership_setup
    ar = AccessRequestFactory(requester_id=data["user_a"].id)
    db_session.add(ar)
    db_session.flush()

    grant = JITAccessGrant(
        user_id=data["user_a"].id,
        role_id=data["role"].id,
        resource_id=data["resource_1"].id,
        target_account_binding_id=data["binding_a"].id,
        command_set_id="system_health_check",
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    with pytest.raises(UnauthorizedActivationError):
        data["service"].activate_grant(grant.id, data["user_b"].id)


def test_user_b_cannot_revoke_user_a_grant(ownership_setup, db_session):
    """Non-admin User B cannot revoke User A's grant."""
    data = ownership_setup
    ar = AccessRequestFactory(requester_id=data["user_a"].id)
    db_session.add(ar)
    db_session.flush()

    grant = JITAccessGrant(
        user_id=data["user_a"].id,
        role_id=data["role"].id,
        resource_id=data["resource_1"].id,
        target_account_binding_id=data["binding_a"].id,
        command_set_id="system_health_check",
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    with pytest.raises(UnauthorizedActivationError):
        data["service"].revoke_access(grant.id, data["user_b"].id)

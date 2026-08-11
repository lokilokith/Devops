"""Tests for JITAccessService."""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.jit_access.service import JITAccessService
from app.jit_access.repository import JITAccessRepository
from app.jit_access.models import JITGrantStatus
from app.jit_access.exceptions import (
    UnauthorizedActivationError,
    InvalidGrantStateError,
    JITAccessError
)
from app.access_requests.models import AccessRequestStatus
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.service import AccessRequestService
from app.policy_engine.service import PolicyService
from app.policy_engine.repository import PolicyRepository
from app.audit.service import AuditService
from app.audit.repository import AuditRepository
from app.authorization.service import AuthorizationService

from tests.fixtures.factories import UserFactory, RoleFactory, ResourceFactory, AccessRequestFactory
from app.jit_access.models import JITAccessGrant

@pytest.fixture(autouse=True)
def setup_permissions(db_session, admin_user):
    from app.permissions.models import Permission, PermissionAction, PermissionStatus
    from app.roles.models import Role, UserRole
    from app.role_permissions.models import RolePermission
    
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

    for action in [PermissionAction.CREATE, PermissionAction.READ, PermissionAction.UPDATE, PermissionAction.DELETE]:
        perm_code = f"PERM_JIT_GRANTS_{action.value.upper()}"
        perm = db_session.query(Permission).filter_by(permission_code=perm_code, action=action).first()
        if not perm:
            perm = Permission(
                permission_code=perm_code,
                permission_name=f"JIT Grants {action.value.capitalize()}",
                action=action, 
                status=PermissionStatus.ACTIVE
            )
            db_session.add(perm)
            db_session.flush()
        db_session.add(RolePermission(role_id=role_id, permission_id=perm.id))
    db_session.commit()

@pytest.fixture
def jit_service(db_session, security_auth_service):
    ar_repo = AccessRequestRepository(db_session)
    # mock the user_repo etc or just pass None if not strictly used in tests
    # Wait, ar_service needs user_repo, role_repo, res_repo. We can mock them or pass real ones.
    from app.identity.repository import IdentityRepository
    from app.roles.repository import RolesRepository
    from app.resources.repository import ResourcesRepository
    from app.user_roles.repository import UserRolesRepository

    ar_service = AccessRequestService(
        ar_repo,
        IdentityRepository(db_session),
        RolesRepository(db_session),
        ResourcesRepository(db_session),
        UserRolesRepository(db_session)
    )
    
    auth_service = AuthorizationService(db_session)
    audit_service = AuditService(AuditRepository(db_session))
    
    policy_service = PolicyService(
        PolicyRepository(db_session),
        auth_service,
        audit_service
    )
    
    return JITAccessService(
        JITAccessRepository(),
        ar_service,
        policy_service,
        audit_service,
        auth_service
    )


def test_request_access_duration_exceeds_limit(jit_service, db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    db_session.add_all([user, role, resource])
    db_session.flush()
    
    # Mock evaluate_policy
    jit_service._policy_service.evaluate_policy = lambda **kwargs: {
        "decision": "ALLOW",
        "max_duration_seconds": 3600 # 1 hour
    }
    
    with pytest.raises(JITAccessError, match="Duration cannot exceed policy limit"):
        jit_service.request_access(
            requester_id=user.id,
            role_id=role.id,
            resource_id=resource.id,
            duration_minutes=120,
            reason="Need access"
        )

def test_request_access_policy_denied(jit_service, db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    db_session.add_all([user, role, resource])
    db_session.flush()
    
    jit_service._policy_service.evaluate_policy = lambda **kwargs: {
        "decision": "DENY",
        "reason": "Explicit deny"
    }
    
    with pytest.raises(JITAccessError, match="Policy denied"):
        jit_service.request_access(user.id, role.id, resource.id, 60, "reason")


def test_requester_cannot_activate_own_grant(jit_service, db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(requester_id=user.id, status=AccessRequestStatus.APPROVED)
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created_grant = JITAccessRepository.create(grant)
    
    # User tries to activate their own grant (assuming they lack admin permissions)
    with pytest.raises(UnauthorizedActivationError):
        jit_service.activate_grant(created_grant.id, user.id)

def test_activate_grant_requires_approved_request(jit_service, db_session, admin_user):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(requester_id=user.id, status=AccessRequestStatus.PENDING)
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created_grant = JITAccessRepository.create(grant)
    
    # Try to activate, should fail because AR is PENDING
    with pytest.raises(InvalidGrantStateError, match="Cannot activate grant. Access request is pending"):
        jit_service.activate_grant(created_grant.id, admin_user.id)

def test_admin_can_activate_others_grant(jit_service, db_session, admin_user):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(requester_id=user.id, status=AccessRequestStatus.APPROVED)
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created_grant = JITAccessRepository.create(grant)
    
    activated = jit_service.activate_grant(created_grant.id, admin_user.id)
    assert activated.status == JITGrantStatus.ACTIVE

def test_non_admin_cannot_revoke_another_users_grant(jit_service, db_session):
    user1 = UserFactory()
    user2 = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user1, user2, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user1.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created = JITAccessRepository.create(grant)
    
    with pytest.raises(UnauthorizedActivationError, match="User cannot revoke another user's grant"):
        jit_service.revoke_access(created.id, user2.id)

def test_revoke_grant(jit_service, db_session, admin_user):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created = JITAccessRepository.create(grant)
    
    revoked = jit_service.revoke_access(created.id, admin_user.id)
    assert revoked.status == JITGrantStatus.REVOKED
    
    # Test Revoked grant cannot access resource
    assert not JITAccessRepository.check_active_grant(user.id, role.id, resource.id)

def test_expired_grant_cannot_access_resource(jit_service, db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    JITAccessRepository.create(grant)
    
    assert not JITAccessRepository.check_active_grant(user.id, role.id, resource.id)

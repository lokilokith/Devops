"""Tests for JIT Access API routes."""

import pytest
from uuid import uuid4
from flask import url_for
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.access_requests.models import AccessRequestStatus
from datetime import datetime, timedelta, timezone

from tests.fixtures.factories import UserFactory, RoleFactory, ResourceFactory, AccessRequestFactory

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
        
        # Give normal users CREATE and READ access only
        if action in [PermissionAction.CREATE, PermissionAction.READ]:
            from app.identity.models import User
            # normal_user is created by normal_user fixture or we can just give it to all users
            # The test uses `normal_token` and `user_token`.
            # We can create a user role for "normal_user" fixture.
            normal_role = db_session.query(Role).filter_by(role_code="TEST_NORMAL").first()
            if not normal_role:
                normal_role = Role(role_code="TEST_NORMAL", role_name="Test Normal")
                db_session.add(normal_role)
                db_session.flush()
            db_session.add(RolePermission(role_id=normal_role.id, permission_id=perm.id))
            
            # assign to normal_user if present
            normal = db_session.query(User).filter_by(username="user0").first() # from UserFactory
            if normal:
                if not db_session.query(UserRole).filter_by(user_id=normal.id, role_id=normal_role.id).first():
                    db_session.add(UserRole(user_id=normal.id, role_id=normal_role.id))
                    
    db_session.commit()

@pytest.fixture(autouse=True)
def setup_normal_user_role(db_session, normal_user):
    from app.roles.models import Role, UserRole
    normal_role = db_session.query(Role).filter_by(role_code="TEST_NORMAL").first()
    if not normal_role:
        normal_role = Role(role_code="TEST_NORMAL", role_name="Test Normal")
        db_session.add(normal_role)
        db_session.flush()
    if not db_session.query(UserRole).filter_by(user_id=normal_user.id, role_id=normal_role.id).first():
        db_session.add(UserRole(user_id=normal_user.id, role_id=normal_role.id))
    db_session.commit()

def test_request_jit_access_unauthorized(client):
    response = client.post("/jit/request", json={})
    assert response.status_code == 401

def test_request_jit_access_missing_fields(client, user_token):
    response = client.post("/jit/request", headers={"Authorization": f"Bearer {user_token}"}, json={})
    assert response.status_code == 400 # marshmallow validation

def test_request_jit_access_success(client, admin_token, admin_user, db_session):
    role = RoleFactory()
    resource = ResourceFactory()
    db_session.add_all([role, resource])
    db_session.flush()

    payload = {
        "user_id": str(admin_user.id),
        "role_id": str(role.id),
        "resource_id": str(resource.id),
        "duration_minutes": 60,
        "reason": "Debugging PROD"
    }

    response = client.post(
        "/jit/request",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload
    )
    assert response.status_code == 201
    assert response.json["status"] == "pending"

def test_request_jit_access_for_another_user_fails(client, normal_token, db_session):
    user2 = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    db_session.add_all([user2, role, resource])
    db_session.flush()

    payload = {
        "user_id": str(user2.id), # normal user requesting for another user
        "role_id": str(role.id),
        "resource_id": str(resource.id),
        "duration_minutes": 60,
        "reason": "Debugging PROD"
    }

    response = client.post(
        "/jit/request",
        headers={"Authorization": f"Bearer {normal_token}"},
        json=payload
    )
    assert response.status_code == 400
    assert "admin privileges" in response.json["message"]

def test_list_grants(client, admin_token, db_session, admin_user):
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=admin_user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    JITAccessRepository.create(grant)

    response = client.get(
        "/jit/grants",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json["total"] >= 1
    
def test_activate_grant(client, admin_token, db_session, admin_user):
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory(status=AccessRequestStatus.APPROVED, requester_id=admin_user.id)
    db_session.add_all([role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=admin_user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created = JITAccessRepository.create(grant)

    response = client.post(
        f"/jit/{created.id}/activate",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json["status"] == "active"

def test_revoke_grant(client, admin_token, db_session, admin_user):
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=admin_user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    created = JITAccessRepository.create(grant)

    response = client.post(
        f"/jit/{created.id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json["status"] == "revoked"

def test_current_session(client, admin_token, db_session, admin_user):
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=admin_user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    JITAccessRepository.create(grant)

    response = client.get(
        "/jit/session/current",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert len(response.json) >= 1
    assert response.json[0]["status"] == "active"

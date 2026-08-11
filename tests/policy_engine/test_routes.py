"""Tests for Policy Engine Routes."""

import pytest
from unittest.mock import patch
from uuid import uuid4

from app.policy_engine.models import AccessPolicy, PolicyEffect


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
        perm = Permission(
            permission_code=f"PERM_POLICIES_{action.value.upper()}",
            permission_name=f"Policies {action.value.capitalize()}",
            action=action
        )
        db_session.add(perm)
        db_session.flush()
        db_session.add(RolePermission(role_id=role_id, permission_id=perm.id))
    db_session.commit()

def test_create_policy_success(client, admin_token, db_session):
    resp = client.post(
        "/policy-engine/policies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Route Policy",
            "conditions": {"allowed_ip_ranges": ["10.0.0.0/8"]},
            "effect": "allow",
            "priority": 5
        }
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "Test Route Policy"

def test_create_policy_invalid_condition(client, admin_token, db_session):
    resp = client.post(
        "/policy-engine/policies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Invalid IP",
            "conditions": {"allowed_ip_ranges": ["invalid_ip"]}
        }
    )
    assert resp.status_code == 422
    assert "Invalid CIDR" in resp.get_json()["message"]

def test_list_policies(client, admin_token, db_session):
    # Ensure one exists
    client.post(
        "/policy-engine/policies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "List Test Policy",
            "conditions": {}
        }
    )
    
    resp = client.get(
        "/policy-engine/policies",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]) > 0

def test_evaluate_endpoint(client, admin_token, db_session):
    resp = client.post(
        "/policy-engine/evaluate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": str(uuid4()),
            "resource_id": "some_resource",
            "action": "read",
            "context": {"ip": "10.0.0.1"}
        }
    )
    # The evaluation might be DENY due to RBAC missing, but it should return 200
    assert resp.status_code == 200
    data = resp.get_json()
    assert "decision" in data["data"]

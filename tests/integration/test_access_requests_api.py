"""Integration tests for the Access Requests API."""

import pytest
from uuid import uuid4
from datetime import datetime
from app.identity.models import User, UserStatus
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.roles.models import Role, RoleType
from app.permissions.models import Permission, PermissionAction
from app.role_permissions.models import RolePermission
from app.roles.models import UserRole


@pytest.fixture
def auth_setup(db_session, app):
    """Setup a user with access_requests permissions and return their token."""
    # Create user
    user = User(
        employee_id="TEST_001",
        username="testuser",
        email="test@local",
        full_name="Test User 1",
        status=UserStatus.ACTIVE,
    )
    auth_svc = AuthService(IdentityRepository(db_session))
    user.password_hash = auth_svc.hash_password("secret")
    db_session.add(user)

    # Create Role
    role = Role(role_code="TEST_ROLE", role_name="Test Role", role_type=RoleType.CUSTOM)
    db_session.add(role)
    db_session.flush()

    perms = ["create", "read", "approve", "reject", "cancel"]
    for p in perms:
        perm = Permission(
            permission_code=f"PERM_ACCESS_REQUESTS_{p.upper()}",
            permission_name=f"access_requests.{p}",
            action=PermissionAction(p),
        )
        db_session.add(perm)
        db_session.flush()
        db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()

    token = auth_svc.generate_access_token(user.id)
    return user, token, role


def test_create_access_request_success(client, db_session, auth_setup):
    """Test creating an access request successfully."""
    user, token, role = auth_setup
    payload = {
        "requested_role_id": str(role.id),
        "business_justification": "Need access to role X for project Y",
        "priority": "high",
    }

    response = client.post(
        "/access-requests", json=payload, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["business_justification"] == payload["business_justification"]
    assert data["data"]["status"] == "pending"


def test_list_access_requests(client, db_session, auth_setup):
    """Test listing access requests."""
    user, token, role = auth_setup
    response = client.get(
        "/access-requests", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_approve_access_request_forbidden(client, db_session):
    """Test approving without approve permission."""
    # Create a user WITHOUT approve permission
    user = User(
        employee_id="TEST_002",
        username="testuser2",
        email="test2@local",
        full_name="Test User 2",
        status=UserStatus.ACTIVE,
    )
    auth_svc = AuthService(IdentityRepository(db_session))
    user.password_hash = auth_svc.hash_password("secret")
    db_session.add(user)
    db_session.commit()
    token = auth_svc.generate_access_token(user.id)

    fake_id = str(uuid4())
    response = client.post(
        f"/access-requests/{fake_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_create_access_request_invalid_data(client, db_session, auth_setup):
    """Test creating an access request with missing role/resource."""
    user, token, role = auth_setup
    payload = {"business_justification": "Need access"}

    response = client.post(
        "/access-requests", json=payload, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 422

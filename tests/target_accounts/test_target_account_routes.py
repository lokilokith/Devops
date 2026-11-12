"""API route tests for Target Account Bindings (/target-accounts)."""

import uuid

import pytest

from app.auth.service import AuthService
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository
from app.permissions.models import Permission, PermissionAction
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.role_permissions.models import RolePermission
from app.roles.models import Role, UserRole
from app.target_accounts.models import (
    TargetAccountBinding,
    TargetAccountBindingStatus,
)


@pytest.fixture
def auth_client(client, db_session):
    """Create test client with authenticated user tokens."""
    admin_user = User(
        employee_id=f"ADM-{uuid.uuid4().hex[:6]}",
        username=f"admin_{uuid.uuid4().hex[:6]}",
        email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Admin User",
        status=UserStatus.ACTIVE,
    )

    regular_user = User(
        employee_id=f"USR-{uuid.uuid4().hex[:6]}",
        username=f"regular_{uuid.uuid4().hex[:6]}",
        email=f"regular_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Regular User",
        status=UserStatus.ACTIVE,
    )

    db_session.add_all([admin_user, regular_user])
    db_session.commit()

    # Create admin role with permissions
    code_suffix = uuid.uuid4().hex[:6]
    admin_role = Role(
        role_code=f"adm_{code_suffix}",
        role_name=f"Admin Role {code_suffix}",
        description="Admin",
    )
    db_session.add(admin_role)
    db_session.commit()

    perm_read = Permission(
        permission_code="PERM_TARGET_ACCOUNTS_READ",
        permission_name=f"Read Target Accounts {code_suffix}",
        action=PermissionAction.READ,
        description="Read target accounts",
    )
    perm_delete = Permission(
        permission_code="PERM_TARGET_ACCOUNTS_DELETE",
        permission_name=f"Delete Target Accounts {code_suffix}",
        action=PermissionAction.DELETE,
        description="Delete target accounts",
    )
    db_session.add_all([perm_read, perm_delete])
    db_session.commit()

    db_session.add(RolePermission(role_id=admin_role.id, permission_id=perm_read.id))
    db_session.add(RolePermission(role_id=admin_role.id, permission_id=perm_delete.id))
    db_session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
    db_session.commit()

    auth_svc = AuthService(IdentityRepository(db_session))
    admin_token = auth_svc.generate_access_token(admin_user.id)
    user_token = auth_svc.generate_access_token(regular_user.id)

    return {
        "client": client,
        "admin_user": admin_user,
        "admin_token": admin_token,
        "regular_user": regular_user,
        "user_token": user_token,
        "session": db_session,
    }


def test_list_target_accounts_regular_user_filtered(auth_client):
    """Test regular user only sees their own target account bindings."""
    c = auth_client["client"]
    token = auth_client["user_token"]
    user = auth_client["regular_user"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    b1 = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res1.id,
        target_os_username="reg_user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    session.add(b1)
    session.commit()

    resp = c.get(
        "/target-accounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["target_os_username"] == "reg_user"


def test_list_target_accounts_admin_all(auth_client):
    """Test admin can view all target account bindings."""
    c = auth_client["client"]
    token = auth_client["admin_token"]
    user = auth_client["regular_user"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    b1 = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res1.id,
        target_os_username="user_on_srv",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    session.add(b1)
    session.commit()

    resp = c.get(
        "/target-accounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


def test_get_target_account_detail_idor_protection(auth_client):
    """Test IDOR protection: User A cannot view User B's binding."""
    c = auth_client["client"]
    user_token = auth_client["user_token"]
    admin = auth_client["admin_user"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    # Binding owned by admin
    admin_binding = TargetAccountBinding(
        control_plane_user_id=admin.id,
        resource_id=res1.id,
        target_os_username="admin_target",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    session.add(admin_binding)
    session.commit()

    # Regular user attempts to read admin's binding
    resp = c.get(
        f"/target-accounts/{admin_binding.id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_get_target_account_detail_success(auth_client):
    """Test owner can view their own binding detail."""
    c = auth_client["client"]
    user_token = auth_client["user_token"]
    user = auth_client["regular_user"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    user_binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res1.id,
        target_os_username="my_target_user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    session.add(user_binding)
    session.commit()

    resp = c.get(
        f"/target-accounts/{user_binding.id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["id"] == str(user_binding.id)


def test_delete_target_account_idor_protection(auth_client):
    """Test non-admin non-owner cannot delete another user's binding."""
    c = auth_client["client"]
    user_token = auth_client["user_token"]
    admin = auth_client["admin_user"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    admin_binding = TargetAccountBinding(
        control_plane_user_id=admin.id,
        resource_id=res1.id,
        target_os_username="admin_target",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    session.add(admin_binding)
    session.commit()

    resp = c.delete(
        f"/target-accounts/{admin_binding.id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_post_target_account_provision_endpoint(auth_client):
    """Test POST /target-accounts API endpoint."""
    c = auth_client["client"]
    user_token = auth_client["user_token"]
    session = auth_client["session"]

    res1 = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name="Server 1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
    )
    session.add(res1)
    session.commit()

    resp = c.post(
        "/target-accounts",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"resource_id": str(res1.id)},
    )
    assert resp.status_code in (201, 200)
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["resource_id"] == str(res1.id)
    assert data["data"]["status"] == "active"

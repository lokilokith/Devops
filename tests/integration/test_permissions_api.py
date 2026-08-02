from uuid import uuid4

from sqlalchemy import select

from app.identity.models import User, UserStatus
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.role_permissions.models import RolePermission
from app.roles.models import Role, RoleStatus, RoleType, UserRole


def setup_admin_user(db_session, app):
    # Create an admin user with permission to hit the endpoint
    u = User(
        employee_id=f"E_{uuid4().hex[:8]}",
        username=f"U_{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@test.local",
        full_name="Admin",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)

    r = Role(
        role_code=f"R_{uuid4().hex[:8]}",
        role_name=f"Role {uuid4().hex[:8]}",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(r)

    # We need permissions for "permissions" resource
    p1 = db_session.scalar(
        select(Permission).where(Permission.permission_code == "PERM_PERMISSIONS_READ")
    )
    if not p1:
        p1 = Permission(
            permission_code="PERM_PERMISSIONS_READ",
            permission_name="permissions.read",
            action=PermissionAction.READ,
        )
        db_session.add(p1)
        db_session.flush()
    p2 = db_session.scalar(
        select(Permission).where(
            Permission.permission_code == "PERM_PERMISSIONS_CREATE"
        )
    )
    if not p2:
        p2 = Permission(
            permission_code="PERM_PERMISSIONS_CREATE",
            permission_name="permissions.create",
            action=PermissionAction.CREATE,
        )
        db_session.add(p2)
        db_session.flush()
    p3 = db_session.scalar(
        select(Permission).where(
            Permission.permission_code == "PERM_PERMISSIONS_UPDATE"
        )
    )
    if not p3:
        p3 = Permission(
            permission_code="PERM_PERMISSIONS_UPDATE",
            permission_name="permissions.update",
            action=PermissionAction.UPDATE,
        )
        db_session.add(p3)
        db_session.flush()
    p4 = db_session.scalar(
        select(Permission).where(
            Permission.permission_code == "PERM_PERMISSIONS_DELETE"
        )
    )
    if not p4:
        p4 = Permission(
            permission_code="PERM_PERMISSIONS_DELETE",
            permission_name="permissions.delete",
            action=PermissionAction.DELETE,
        )
        db_session.add(p4)
        db_session.flush()
    db_session.add_all([p1, p2, p3, p4])

    db_session.commit()

    db_session.add(UserRole(user_id=u.id, role_id=r.id))
    db_session.add(RolePermission(role_id=r.id, permission_id=p1.id))
    db_session.add(RolePermission(role_id=r.id, permission_id=p2.id))
    db_session.add(RolePermission(role_id=r.id, permission_id=p3.id))
    db_session.add(RolePermission(role_id=r.id, permission_id=p4.id))
    db_session.commit()

    from tests.api.test_decorators import create_mock_token

    token = create_mock_token(app, u.id)
    return token


def setup_limited_user(db_session, app):
    u = User(
        employee_id=f"E_{uuid4().hex[:8]}",
        username=f"U_{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@test.local",
        full_name="Limited",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    from tests.api.test_decorators import create_mock_token

    token = create_mock_token(app, u.id)
    return token


def test_permissions_crud(client, db_session, app):
    token = setup_admin_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Permission
    create_data = {
        "permission_code": "PERM_TEST_READ",
        "permission_name": "test.read",
        "action": "read",
        "description": "Test read permission",
    }
    res = client.post("/permissions", json=create_data, headers=headers)
    assert res.status_code == 201
    perm_id = res.json["data"]["id"]

    from uuid import UUID

    db_perm = db_session.get(Permission, UUID(perm_id))
    assert db_perm is not None
    assert db_perm.permission_code == "PERM_TEST_READ"

    # 2. Duplicate Creation should fail
    res_dup = client.post("/permissions", json=create_data, headers=headers)
    assert res_dup.status_code in (400, 409, 422)  # Should be rejected

    # 3. Read Permissions
    res_list = client.get("/permissions", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["data"]) >= 1

    # 4. Get specific permission
    res_get = client.get(f"/permissions/{perm_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json["data"]["permission_code"] == "PERM_TEST_READ"

    # 5. Update Permission
    update_data = {
        "permission_name": "test.read.updated",
        "action": "read",
        "status": "inactive",
    }
    res_put = client.put(f"/permissions/{perm_id}", json=update_data, headers=headers)
    assert res_put.status_code == 200

    db_session.refresh(db_perm)
    assert db_perm.permission_name == "test.read.updated"
    assert db_perm.status == PermissionStatus.INACTIVE

    # 6. Delete Permission
    res_del = client.delete(f"/permissions/{perm_id}", headers=headers)
    assert res_del.status_code == 200

    assert db_session.get(Permission, UUID(perm_id)) is None


def test_permissions_authorization(client, db_session, app):
    token = setup_limited_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}

    # Should be 403 Forbidden
    res = client.get("/permissions", headers=headers)
    assert res.status_code == 403

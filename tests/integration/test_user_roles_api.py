from uuid import UUID

import pytest

from app.extensions import db
from app.identity.models import User, UserStatus
from app.permissions.models import Permission, PermissionAction
from app.role_permissions.models import RolePermission
from app.roles.models import Role, RoleStatus, RoleType, UserRole


def setup_admin_user(db_session, app):
    u = User(
        employee_id="ADM3",
        username="admin_ur_int",
        email="admin_ur@test.com",
        full_name="Admin",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)

    r = Role(
        role_code="ADMIN_UR_INT",
        role_name="Admin UR Int",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(r)

    p1 = Permission(
        permission_code="PERM_USER_ROLES_MANAGE",
        permission_name="user_roles.manage",
        action=PermissionAction.MANAGE,
    )
    db_session.add_all([p1])

    db_session.commit()

    db_session.add(UserRole(user_id=u.id, role_id=r.id))
    db_session.add(RolePermission(role_id=r.id, permission_id=p1.id))
    db_session.commit()

    from tests.api.test_decorators import create_mock_token

    token = create_mock_token(app, u.id)
    return token, u.id


def setup_limited_user(db_session, app):
    u = User(
        employee_id="LIM3",
        username="limited_ur_int",
        email="lim_ur_int@test.com",
        full_name="Limited",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    from tests.api.test_decorators import create_mock_token

    token = create_mock_token(app, u.id)
    return token, u.id


def test_user_roles_crud(client, db_session, app):
    token, admin_id = setup_admin_user(db_session, app)
    _, target_user_id = setup_limited_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}

    # Need a role to assign
    role = Role(
        role_code="ASSIGN_ROLE",
        role_name="Assign Role",
        role_type=RoleType.CUSTOM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(role)
    db_session.commit()

    # 1. Assign Role to User
    assign_data = {"role_id": str(role.id)}
    res = client.post(
        f"/users/{target_user_id}/roles", json=assign_data, headers=headers
    )
    assert res.status_code == 201

    # Verify DB state
    db_ur = (
        db_session.query(UserRole)
        .filter_by(user_id=target_user_id, role_id=role.id)
        .first()
    )
    assert db_ur is not None

    # 2. Duplicate Assignment should fail (Business Rule)
    res_dup = client.post(
        f"/users/{target_user_id}/roles", json=assign_data, headers=headers
    )
    assert res_dup.status_code in (400, 409, 422)  # Should be rejected

    # 3. List User Roles
    res_list = client.get(f"/users/{target_user_id}/roles", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["data"]) >= 1

    # 4. Remove Role
    res_del = client.delete(f"/users/{target_user_id}/roles/{role.id}", headers=headers)
    assert res_del.status_code == 200

    assert (
        db_session.query(UserRole)
        .filter_by(user_id=target_user_id, role_id=role.id)
        .first()
        is None
    )


def test_user_roles_authorization(client, db_session, app):
    token, lim_id = setup_limited_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}

    # Should be 403 Forbidden
    res = client.get(f"/users/{lim_id}/roles", headers=headers)
    assert res.status_code == 403

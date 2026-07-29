import pytest
from app.roles.models import Role, RoleType, RoleStatus, UserRole
from app.identity.models import User, UserStatus
from app.permissions.models import Permission, PermissionAction
from app.role_permissions.models import RolePermission
from app.extensions import db
from uuid import UUID

def setup_admin_user(db_session, app):
    u = User(employee_id="ADM4", username="admin_rp_int", email="admin_rp@test.com", full_name="Admin", status=UserStatus.ACTIVE)
    db_session.add(u)
    
    r = Role(role_code="ADMIN_RP_INT", role_name="Admin RP Int", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    db_session.add(r)
    
    p1 = Permission(permission_code="PERM_ROLE_PERMISSIONS_READ", permission_name="role_permissions.read", action=PermissionAction.READ)
    p2 = Permission(permission_code="PERM_ROLE_PERMISSIONS_CREATE", permission_name="role_permissions.create", action=PermissionAction.CREATE)
    p3 = Permission(permission_code="PERM_ROLE_PERMISSIONS_DELETE", permission_name="role_permissions.delete", action=PermissionAction.DELETE)
    p4 = Permission(permission_code="PERM_ROLE_PERMISSIONS_MANAGE", permission_name="role_permissions.manage", action=PermissionAction.CREATE)
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
    return token, r.id

def setup_limited_user(db_session, app):
    u = User(employee_id="LIM4", username="limited_rp_int", email="lim_rp_int@test.com", full_name="Limited", status=UserStatus.ACTIVE)
    db_session.add(u)
    db_session.commit()
    from tests.api.test_decorators import create_mock_token
    token = create_mock_token(app, u.id)
    return token

def test_role_permissions_crud(client, db_session, app):
    token, admin_role_id = setup_admin_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Need a permission to assign
    perm = Permission(permission_code="PERM_TO_ASSIGN", permission_name="assign.me", action=PermissionAction.READ)
    db_session.add(perm)
    db_session.commit()
    
    # 1. Assign Permission to Role
    assign_data = {
        "permission_id": str(perm.id)
    }
    res = client.post(f"/roles/{admin_role_id}/permissions", json=assign_data, headers=headers)
    assert res.status_code == 201
    
    # Verify DB state
    db_rp = db_session.query(RolePermission).filter_by(role_id=admin_role_id, permission_id=perm.id).first()
    assert db_rp is not None
    
    # 2. Duplicate Assignment should fail
    res_dup = client.post(f"/roles/{admin_role_id}/permissions", json=assign_data, headers=headers)
    assert res_dup.status_code in (400, 409, 422) # Should be rejected
    
    # 3. List Role Permissions
    res_list = client.get(f"/roles/{admin_role_id}/permissions", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["data"]) >= 1
    
    # 4. Remove Permission
    res_del = client.delete(f"/roles/{admin_role_id}/permissions/{perm.id}", headers=headers)
    assert res_del.status_code == 200
    
    assert db_session.query(RolePermission).filter_by(role_id=admin_role_id, permission_id=perm.id).first() is None

def test_role_permissions_authorization(client, db_session, app):
    token = setup_limited_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}
    
    from uuid import uuid4
    res = client.get(f"/roles/{uuid4()}/permissions", headers=headers)
    assert res.status_code == 403

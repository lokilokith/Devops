import pytest
from app.resources.models import Resource, ResourceType, ResourceStatus
from app.identity.models import User, UserStatus
from app.roles.models import Role, RoleType, RoleStatus, UserRole
from app.permissions.models import Permission, PermissionAction
from app.role_permissions.models import RolePermission
from app.extensions import db
from uuid import UUID

def setup_admin_user(db_session, app):
    u = User(employee_id="ADM2", username="admin_res_int", email="admin_res@test.com", full_name="Admin", status=UserStatus.ACTIVE)
    db_session.add(u)
    
    r = Role(role_code="ADMIN_RES_INT", role_name="Admin Res Int", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    db_session.add(r)
    
    p1 = Permission(permission_code="PERM_RESOURCES_READ", permission_name="resources.read", action=PermissionAction.READ)
    p2 = Permission(permission_code="PERM_RESOURCES_CREATE", permission_name="resources.create", action=PermissionAction.CREATE)
    p3 = Permission(permission_code="PERM_RESOURCES_UPDATE", permission_name="resources.update", action=PermissionAction.UPDATE)
    p4 = Permission(permission_code="PERM_RESOURCES_DELETE", permission_name="resources.delete", action=PermissionAction.DELETE)
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
    u = User(employee_id="LIM2", username="limited_res_int", email="lim_res_int@test.com", full_name="Limited", status=UserStatus.ACTIVE)
    db_session.add(u)
    db_session.commit()
    from tests.api.test_decorators import create_mock_token
    token = create_mock_token(app, u.id)
    return token

def test_resources_crud(client, db_session, app):
    token = setup_admin_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Create Resource
    create_data = {
        "resource_code": "RES_TEST_1",
        "resource_name": "Test Resource",
        "description": "Test read resource",
        "resource_type": "application"
    }
    res = client.post("/resources", json=create_data, headers=headers)
    assert res.status_code == 201
    res_id = res.json["data"]["id"]
    
    # Verify DB state
    db_res = db_session.get(Resource, UUID(res_id))
    assert db_res is not None
    assert db_res.resource_code == "RES_TEST_1"
    
    # 2. Duplicate Creation should fail
    res_dup = client.post("/resources", json=create_data, headers=headers)
    assert res_dup.status_code in (400, 409, 422) # Should be rejected
    
    # 3. Read Resources
    res_list = client.get("/resources", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["data"]) >= 1
    
    # 4. Get specific resource
    res_get = client.get(f"/resources/{res_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json["data"]["resource_code"] == "RES_TEST_1"
    
    # 5. Update Resource
    update_data = {
        "resource_name": "Updated Test Resource",
        "resource_type": "application",
        "status": "inactive"
    }
    res_put = client.put(f"/resources/{res_id}", json=update_data, headers=headers)
    assert res_put.status_code == 200
    
    db_session.refresh(db_res)
    assert db_res.resource_name == "Updated Test Resource"
    assert db_res.status == ResourceStatus.INACTIVE
    
    # 6. Delete Resource
    res_del = client.delete(f"/resources/{res_id}", headers=headers)
    assert res_del.status_code == 200
    
    assert db_session.get(Resource, UUID(res_id)) is None

def test_resources_authorization(client, db_session, app):
    token = setup_limited_user(db_session, app)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Should be 403 Forbidden
    res = client.get("/resources", headers=headers)
    assert res.status_code == 403

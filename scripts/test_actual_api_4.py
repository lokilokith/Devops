import sys
sys.path.insert(0, ".")

import os
os.environ["APP_ENV"] = "testing"

# Mock decorators before create_app
import app.api.decorators
def mock_login_required(f): return f
def mock_requires_permission(*args, **kwargs): return lambda f: f
app.api.decorators.login_required = mock_login_required
app.api.decorators.requires_permission = mock_requires_permission

from app import create_app
from app.extensions import db
from app.roles.models import Role
from app.permissions.models import Permission
from app.role_permissions.models import RolePermission
import uuid
import json

app = create_app()

with app.app_context():
    db.create_all()
    db.session.query(RolePermission).delete()
    db.session.query(Role).delete()
    db.session.query(Permission).delete()
    db.session.commit()
    
    r_id = uuid.uuid4()
    p_id = uuid.uuid4()
    r = Role(id=r_id, role_code="TEST_ROLE", role_name="Test Role", description="test", status="active")
    p = Permission(id=p_id, permission_code="TEST_PERM", permission_name="Test Perm", action="read")
    rp = RolePermission(role_id=r_id, permission_id=p_id)
    db.session.add_all([r, p, rp])
    db.session.commit()

    with app.test_client() as client:
        res = client.get(f"/permissions/{p_id}/roles")
        print("Status:", res.status_code)
        print("JSON:", json.dumps(res.json, indent=2))

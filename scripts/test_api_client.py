import sys
sys.path.insert(0, ".")

import os
os.environ["APP_ENV"] = "testing"

import json
from unittest.mock import patch
from app import create_app
from app.extensions import db
from app.roles.models import Role
from app.permissions.models import Permission
from app.role_permissions.models import RolePermission
import uuid

app = create_app()

with app.app_context():
    # Clear tables
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

    with patch('flask_jwt_extended.verify_jwt_in_request'):
        with patch('flask_jwt_extended.get_jwt_identity', return_value="admin"):
            with patch('app.api.decorators.check_permission', return_value=True):
                with app.test_client() as client:
                    res = client.get(f"/permissions/{p_id}/roles")
                    print("Status Code:", res.status_code)
                    print("Response JSON:")
                    print(json.dumps(res.json, indent=2))

import sys
sys.path.insert(0, ".")

import os
os.environ["APP_ENV"] = "testing"
os.environ["JWT_SECRET_KEY"] = "super-secret"

from app import create_app
from app.extensions import db
from app.roles.models import Role
from app.permissions.models import Permission
from app.role_permissions.models import RolePermission
import uuid
import json
from flask_jwt_extended import create_access_token

app = create_app()
with app.app_context():
    # Setup
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

    token = create_access_token(identity="11111111-1111-1111-1111-111111111111")
    
    from unittest.mock import patch
    with patch('app.api.decorators.AuthorizationService.has_permission', return_value=True):
        with app.test_client() as client:
            res = client.get(
                f"/permissions/{p_id}/roles",
                headers={"Authorization": f"Bearer {token}"}
            )
            print("Status:", res.status_code)
            print("JSON:", json.dumps(res.json, indent=2))

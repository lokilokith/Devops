import sys
sys.path.insert(0, ".")

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
    
    r = Role(id=r_id, role_code="ADMIN", role_name="Administrator", description="test", status="active")
    p = Permission(id=p_id, permission_code="READ", permission_name="Read", action="read")
    rp = RolePermission(role_id=r_id, permission_id=p_id)
    
    db.session.add_all([r, p, rp])
    db.session.commit()
    
    with app.test_client() as client:
        # We need auth. Let's mock the login_required decorator or just use it.
        # Actually, let's just bypass auth for the test or mock it.
        pass

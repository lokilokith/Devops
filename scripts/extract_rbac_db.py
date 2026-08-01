import os
import sys

os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "postgresql://opsforge_test:opsforge_test@localhost:5440/opsforge_test"

from app import create_app
from app.extensions import db
from app.roles.models import Role
from app.permissions.models import Permission
from app.role_permissions.models import RolePermission
import json

def verify_permissions():
    app = create_app()
    with app.app_context():
        db.create_all() # ensure tables exist if not already seeded
        
        # We need to make sure the seed script ran, otherwise it will be empty
        roles = db.session.query(Role).all()
        if not roles:
            from app.security.bootstrap import seed_rbac
            seed_rbac()
            roles = db.session.query(Role).all()
            
        matrix = []
        for r in roles:
            perms = db.session.query(Permission).join(
                RolePermission, RolePermission.permission_id == Permission.id
            ).filter(RolePermission.role_id == r.id).all()
            
            for p in perms:
                matrix.append({
                    "role": r.role_code,
                    "permission": p.permission_code,
                    "permission_name": p.permission_name
                })
                
        all_perms = db.session.query(Permission).all()
        orphans = [p.permission_name for p in all_perms if not any(m['permission_name'] == p.permission_name for m in matrix)]
        orphan_roles = [r.role_code for r in roles if not any(m['role'] == r.role_code for m in matrix)]
        
        print("MATRIX:")
        print(json.dumps(matrix, indent=2))
        print("ORPHAN_PERMISSIONS:")
        print(json.dumps(orphans, indent=2))
        print("ORPHAN_ROLES:")
        print(json.dumps(orphan_roles, indent=2))

if __name__ == "__main__":
    verify_permissions()

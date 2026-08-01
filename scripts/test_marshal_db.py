import sys
sys.path.insert(0, ".")

from flask import Flask
from app.extensions import db
from app.roles.models import Role
from app.permissions.models import Permission
from app.role_permissions.models import RolePermission
from app.role_permissions.schemas import permission_roles_list_response_model
from flask_restx import marshal
import uuid

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

db.init_app(app)

with app.app_context():
    db.create_all()
    
    r_id = uuid.uuid4()
    p_id = uuid.uuid4()
    
    r = Role(id=r_id, role_code="ADMIN", role_name="Administrator", description="test", status="active")
    p = Permission(id=p_id, permission_code="READ", permission_name="Read", action="read")
    rp = RolePermission(role_id=r_id, permission_id=p_id)
    
    db.session.add_all([r, p, rp])
    db.session.commit()
    
    from sqlalchemy import select
    stmt = (
        select(Role)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .where(RolePermission.permission_id == p_id)
        .order_by(RolePermission.assigned_at.desc())
    )
    roles = db.session.execute(stmt).scalars().all()
    print("Roles from DB:", roles)
    print("Role 0 type:", type(roles[0]))
    print("Role 0 id:", roles[0].id)
    
    response = {
        "success": True,
        "message": "Success",
        "data": roles
    }
    
    result = marshal(response, permission_roles_list_response_model)
    print("Marshaled Result:")
    print(result)

import sys
sys.path.insert(0, ".")

import json
from flask import Flask
from flask_restx import Api, Resource, Namespace, fields
from app.roles.models import Role
from app.roles.schemas import role_model, roles_ns
import uuid

app = Flask(__name__)
api = Api(app)
ns = Namespace("role_permissions", path="/test")

# ADD BOTH NAMESPACES
api.add_namespace(roles_ns)
api.add_namespace(ns)

permission_roles_list_response_model = ns.model("PermissionRolesListResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.List(fields.Nested(role_model)),
    "meta": fields.Raw
})

@ns.route("/")
class TestResource(Resource):
    @ns.marshal_with(permission_roles_list_response_model)
    def get(self):
        r = Role(id=uuid.uuid4(), role_code="ADMIN", role_name="Administrator", description="test", status="active")
        return {
            "success": True,
            "message": "Success",
            "data": [r]
        }, 200

with app.test_client() as client:
    res = client.get("/test/")
    print("Data:", json.dumps(res.json, indent=2))

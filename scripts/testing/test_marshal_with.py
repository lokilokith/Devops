import sys
sys.path.insert(0, ".")

import json
from flask import Flask
from flask_restx import Api, Resource, Namespace, fields, marshal_with
from app.roles.schemas import role_model
from app.roles.models import Role
import uuid

app = Flask(__name__)
api = Api(app)
ns = Namespace("test")
api.add_namespace(ns)

permission_roles_list_response_model = ns.model("PermissionRolesListResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.List(fields.Nested(role_model)),
    "meta": fields.Raw
})

@ns.route("/test")
class TestResource(Resource):
    @ns.marshal_with(permission_roles_list_response_model)
    def get(self):
        r = Role(id=uuid.uuid4(), role_code="ADMIN", role_name="Administrator", description="test", status="active")
        
        # Simulate success_response
        response = {
            "success": True,
            "message": "Success",
            "data": [r]
        }
        return response, 200

with app.test_client() as client:
    res = client.get("/test")
    print(res.json)

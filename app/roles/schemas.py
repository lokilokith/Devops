"""Roles REST API Schemas."""
from flask_restx import Namespace, fields

roles_ns = Namespace("roles", description="Roles management operations")

role_base = {
    "role_code": fields.String(description="Role Code", example="ADMIN"),
    "role_name": fields.String(description="Role Name", example="Administrator"),
    "description": fields.String(description="Description", example="Super user role"),
    "status": fields.String(description="Status", example="active")
}

role_model = roles_ns.model("Role", {
    "id": fields.String(description="Role UUID", example="12345678-1234-5678-1234-567812345678"),
    **role_base
})

role_create_model = roles_ns.model("RoleCreate", {
    "role_code": fields.String(required=True, description="Role Code"),
    "role_name": fields.String(required=True, description="Role Name"),
    "description": fields.String(required=False, description="Description")
})

role_update_model = roles_ns.model("RoleUpdate", {
    "role_name": fields.String(required=True, description="Role Name"),
    "description": fields.String(required=False, description="Description"),
    "status": fields.String(required=True, description="Status", example="active")
})

role_patch_model = roles_ns.model("RolePatch", {
    "role_name": fields.String(description="Role Name"),
    "description": fields.String(description="Description"),
    "status": fields.String(description="Status", example="active")
})

role_response_model = roles_ns.model("RoleResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.Nested(role_model),
    "meta": fields.Raw
})

role_list_response_model = roles_ns.model("RoleListResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.List(fields.Nested(role_model)),
    "meta": fields.Raw
})

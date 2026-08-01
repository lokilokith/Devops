"""Permissions REST API Schemas."""

from flask_restx import Namespace, fields

permissions_ns = Namespace(
    "permissions", description="Permissions management operations"
)

permission_base = {
    "permission_code": fields.String(
        description="Permission Code", example="PERM_CREATE"
    ),
    "permission_name": fields.String(
        description="Permission Name", example="Permission Create"
    ),
    "description": fields.String(
        description="Description", example="Allows creating resources"
    ),
    "action": fields.String(description="Action", example="create"),
    "status": fields.String(description="Status", example="active"),
}

permission_model = permissions_ns.model(
    "Permission",
    {
        "id": fields.String(
            description="Permission UUID",
            example="12345678-1234-5678-1234-567812345678",
        ),
        **permission_base,
    },
)

permission_create_model = permissions_ns.model(
    "PermissionCreate",
    {
        "permission_code": fields.String(required=True, description="Permission Code"),
        "permission_name": fields.String(required=True, description="Permission Name"),
        "description": fields.String(required=False, description="Description"),
        "action": fields.String(required=False, description="Action", example="create"),
    },
)

permission_update_model = permissions_ns.model(
    "PermissionUpdate",
    {
        "permission_name": fields.String(required=True, description="Permission Name"),
        "description": fields.String(required=False, description="Description"),
        "action": fields.String(required=True, description="Action", example="create"),
        "status": fields.String(required=True, description="Status", example="active"),
    },
)

permission_patch_model = permissions_ns.model(
    "PermissionPatch",
    {
        "permission_name": fields.String(description="Permission Name"),
        "description": fields.String(description="Description"),
        "action": fields.String(description="Action", example="create"),
        "status": fields.String(description="Status", example="active"),
    },
)

permission_response_model = permissions_ns.model(
    "PermissionResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(permission_model),
        "meta": fields.Raw,
    },
)

permission_list_response_model = permissions_ns.model(
    "PermissionListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(permission_model)),
        "meta": fields.Raw,
    },
)

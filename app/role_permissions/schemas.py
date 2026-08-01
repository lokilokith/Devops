"""RolePermissions REST API Schemas."""

from flask_restx import Namespace, fields
from app.permissions.schemas import permission_model
from app.roles.schemas import role_model

role_permissions_ns = Namespace(
    "role_permissions", description="Role Permissions management operations"
)

role_permission_request_model = role_permissions_ns.model(
    "RolePermissionRequest",
    {
        "permission_id": fields.String(
            required=True, description="The UUID of the permission to assign"
        )
    },
)

role_permission_response_model = role_permissions_ns.model(
    "RolePermissionResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Raw,
        "meta": fields.Raw,
    },
)

role_permissions_list_response_model = role_permissions_ns.model(
    "RolePermissionsListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(permission_model)),
        "meta": fields.Raw,
    },
)

permission_roles_list_response_model = role_permissions_ns.model(
    "PermissionRolesListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(role_model)),
        "meta": fields.Raw,
    },
)

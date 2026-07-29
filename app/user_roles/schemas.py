"""UserRoles REST API Schemas."""
from flask_restx import Namespace, fields
from app.roles.schemas import role_model
from app.identity.schemas import user_response_model

user_roles_ns = Namespace("user_roles", description="User Roles management operations")

user_role_response_model = user_roles_ns.model("UserRoleResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.Raw,
    "meta": fields.Raw
})

user_roles_list_response_model = user_roles_ns.model("UserRolesListResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.List(fields.Nested(role_model)),
    "meta": fields.Raw
})

role_users_list_response_model = user_roles_ns.model("RoleUsersListResponse", {
    "success": fields.Boolean,
    "message": fields.String,
    "data": fields.List(fields.Nested(user_response_model)),
    "meta": fields.Raw
})

"""Identity REST API Schemas."""

from flask_restx import Namespace, fields

identity_ns = Namespace("users", description="Identity management operations")

user_base = {
    "employee_id": fields.String(description="Employee ID", example="E12345"),
    "username": fields.String(description="Username", example="johndoe"),
    "email": fields.String(description="Email", example="john.doe@example.com"),
    "full_name": fields.String(description="Full Name", example="John Doe"),
    "title": fields.String(description="Job Title", example="Engineer"),
    "manager_user_id": fields.String(
        description="Manager UUID", example="12345678-1234-5678-1234-567812345678"
    ),
    "status": fields.String(
        description="Status", example="active", attribute="status_value"
    ),
}

user_model = identity_ns.model(
    "User",
    {
        "id": fields.String(
            description="User UUID", example="12345678-1234-5678-1234-567812345678"
        ),
        **user_base,
        "last_login_at": fields.String(
            description="Last login timestamp", example="2023-01-01T12:00:00Z"
        ),
    },
)

user_create_model = identity_ns.model(
    "UserCreate",
    {
        "employee_id": fields.String(required=True, description="Employee ID"),
        "username": fields.String(required=True, description="Username"),
        "email": fields.String(required=True, description="Email"),
        "full_name": fields.String(required=True, description="Full Name"),
        "password": fields.String(required=True, description="Password"),
        "title": fields.String(required=False, description="Job Title"),
        "manager_user_id": fields.String(required=False, description="Manager UUID"),
    },
)

user_update_model = identity_ns.model(
    "UserUpdate",
    {
        "full_name": fields.String(required=True, description="Full Name"),
        "title": fields.String(required=False, description="Job Title"),
        "status": fields.String(required=True, description="Status", example="active"),
    },
)

user_patch_model = identity_ns.model(
    "UserPatch",
    {
        "full_name": fields.String(description="Full Name"),
        "title": fields.String(description="Job Title"),
        "status": fields.String(description="Status", example="active"),
    },
)

user_response_model = identity_ns.model(
    "UserResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(user_model),
        "meta": fields.Raw,
    },
)

user_list_response_model = identity_ns.model(
    "UserListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(user_model)),
        "meta": fields.Raw,
    },
)

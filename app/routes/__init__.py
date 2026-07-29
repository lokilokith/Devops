"""OpsForge Routes Blueprint.

Initializes the API Blueprint, handles global errors,
and mounts namespaces.
"""

from flask import Blueprint
from flask_restx import Api

from app.routes.health_routes import ns as health_ns
from app.identity.routes import identity_ns
from app.roles.routes import roles_ns
from app.resources.routes import resources_ns
from app.permissions.routes import permissions_ns
from app.role_permissions.routes import role_permissions_ns
from app.user_roles.routes import user_roles_ns
from app.auth.routes import auth_ns

from app.shared.exceptions import (DatabaseOperationException,
                                   InvalidStatusTransition,
                                   ResourceNotFoundException,
                                   ValidationException)

blueprint = Blueprint("api", __name__, url_prefix="")


class CustomApi(Api):
    """Custom Flask-RESTX Api to handle domain exceptions."""

    def handle_error(self, e):
        # 1. Handle Flask-RESTX Internal Payload Validation errors
        if (
            hasattr(e, "data")
            and isinstance(e.data, dict)
            and ("errors" in e.data or "message" in e.data)
        ):
            errors_data = e.data.get("errors", [])
            errors_list = []
            if isinstance(errors_data, dict):
                for field, msg in errors_data.items():
                    errors_list.append(f"{field}: {msg}")
            elif isinstance(errors_data, list):
                errors_list = errors_data
            elif errors_data:
                errors_list = [str(errors_data)]
            else:
                errors_list = (
                    [e.description]
                    if hasattr(e, "description")
                    else [str(e)]
                )

            e.data = {
                "success": False,
                "message": e.data.get(
                    "message",
                    "Input payload validation failed",
                ),
                "errors": errors_list,
            }
            return super().handle_error(e)

        # 2. Map Service Layer Domain Exceptions
        if isinstance(e, ResourceNotFoundException):
            return self.make_response(
                {
                    "success": False,
                    "message": str(e),
                    "errors": [str(e)],
                },
                404,
            )

        if isinstance(e, ValidationException):
            return self.make_response(
                {
                    "success": False,
                    "message": str(e),
                    "errors": [str(e)],
                },
                400,
            )

        if isinstance(e, InvalidStatusTransition):
            return self.make_response(
                {
                    "success": False,
                    "message": str(e),
                    "errors": [str(e)],
                },
                400,
            )

        if isinstance(e, DatabaseOperationException):
            return self.make_response(
                {
                    "success": False,
                    "message": "A database operation failed.",
                    "errors": [str(e)],
                },
                500,
            )

        # 3. Fallback to standard HTTP exception handling
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            description = (
                e.description
                or "An unexpected server error occurred."
            )
            return self.make_response(
                {
                    "success": False,
                    "message": getattr(e, "name", "HTTP Error"),
                    "errors": [description],
                },
                e.code,
            )

        # 4. Fallback for unhandled raw Python exceptions
        return self.make_response(
            {
                "success": False,
                "message": "An unexpected server error occurred.",
                "errors": [str(e)],
            },
            500,
        )


authorizations = {
    "Bearer": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": "Enter your JWT token in the format: Bearer <token>"
    }
}

api = CustomApi(
    blueprint,
    title="OpsForge Platform API",
    version="0.1.0",
    description="Enterprise Privileged Access Management API.",
    doc="/docs",
    authorizations=authorizations,
    security="Bearer",
    add_specs=True,
)

# Register namespaces with explicit routing prefix paths
api.add_namespace(health_ns, path="/health")
api.add_namespace(auth_ns, path="/auth")
api.add_namespace(identity_ns, path="/users")
api.add_namespace(roles_ns, path="/roles")
api.add_namespace(resources_ns, path="/resources")
api.add_namespace(permissions_ns, path="/permissions")
api.add_namespace(role_permissions_ns, path="/")
api.add_namespace(user_roles_ns, path="/")


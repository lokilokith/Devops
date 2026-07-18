"""OpsForge Routes Blueprint.

Initializes the API Blueprint, handles global errors, and mounts namespaces.
"""

from flask import Blueprint
from flask_restx import Api
from app.routes.threat_routes import ns as threat_ns
from app.routes.stats_routes import ns as stats_ns
from app.routes.health_routes import ns as health_ns
from app.shared.exceptions import (
    ValidationException,
    ThreatNotFoundException,
    InvalidStatusTransition,
    DatabaseOperationException,
)

blueprint = Blueprint("api", __name__, url_prefix="")


class CustomApi(Api):
    """Custom Flask-RESTX Api class to override validation and business exceptions."""

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
                errors_list = [e.description] if hasattr(e, "description") else [str(e)]

            e.data = {
                "success": False,
                "message": e.data.get("message", "Input payload validation failed"),
                "errors": errors_list,
            }
            return super().handle_error(e)

        # 2. Map Service Layer Domain Exceptions
        if isinstance(e, ThreatNotFoundException):
            return self.make_response(
                {"success": False, "message": str(e), "errors": [str(e)]}, 404
            )

        if isinstance(e, ValidationException):
            return self.make_response(
                {"success": False, "message": str(e), "errors": [str(e)]}, 400
            )

        if isinstance(e, InvalidStatusTransition):
            return self.make_response(
                {"success": False, "message": str(e), "errors": [str(e)]}, 400
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
            description = e.description or "An unexpected server error occurred."
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


api = CustomApi(
    blueprint,
    title="OpsForge Platform API",
    version="0.1.0",
    description="A portfolio-quality DevSecOps backend foundation for OpsForge.",
    doc="/docs",
    add_specs=True,
)

# Register namespaces with explicit routing prefix paths
api.add_namespace(threat_ns, path="/threats")
api.add_namespace(stats_ns, path="/stats")
api.add_namespace(health_ns, path="/health")

"""OpsForge Routes Blueprint.

Initializes the API Blueprint and mounts namespaces.
"""

from flask import Blueprint
from flask_restx import Api
from app.routes.threat_routes import ns as threat_ns
from app.routes.stats_routes import ns as stats_ns
from app.routes.health_routes import ns as health_ns

blueprint = Blueprint("api", __name__, url_prefix="")


class CustomApi(Api):
    """Custom Flask-RESTX Api class to override validation error format."""

    def handle_error(self, e):
        # Intercept and format Flask-RESTX validation errors
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


api = CustomApi(
    blueprint,
    title="OpsForge Threat Intelligence Management API",
    version="0.1.0",
    description="A portfolio-quality DevSecOps Threat Intelligence Management Platform API",
    doc="/docs",
    add_specs=True,
)

# Register namespaces with explicit routing prefix paths
api.add_namespace(threat_ns, path="/threats")
api.add_namespace(stats_ns, path="/threats/stats")
api.add_namespace(health_ns, path="/health")

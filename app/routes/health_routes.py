"""OpsForge Health Endpoint Route.

Defines the health check namespace and database connectivity validation.
"""

import time
import os
from flask import current_app
from flask_restx import Namespace, Resource, fields
from sqlalchemy import text
from app.extensions import db

# Namespace definition
ns = Namespace("health", description="System health and telemetry check")

# Record start time for uptime tracking
start_time = time.time()

# Swagger Models
health_data_model = ns.model(
    "HealthData",
    {
        "application": fields.String(
            description="Application status", example="healthy"
        ),
        "database": fields.String(description="Database status", example="healthy"),
        "environment": fields.String(
            description="Active environment", example="development"
        ),
        "version": fields.String(description="Application version", example="0.1.0"),
        "uptime": fields.Float(
            description="Application uptime in seconds", example=120.45
        ),
    },
)

health_response_model = ns.model(
    "HealthResponse",
    {
        "success": fields.Boolean(description="Indicates success status", example=True),
        "message": fields.String(
            description="Operation feedback message",
            example="System status check executed successfully",
        ),
        "data": fields.Nested(health_data_model),
    },
)


@ns.route("")
class HealthResource(Resource):
    """Resource managing system health telemetry checks."""

    @ns.doc(
        "check_health",
        description="Checks application status and database connectivity",
    )
    @ns.marshal_with(health_response_model, code=200)
    def get(self) -> dict:
        """Retrieves system and database vitality metrics."""
        # Read application version from root VERSION file
        version = "0.1.0"
        try:
            root_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            version_path = os.path.join(root_dir, "VERSION")
            if os.path.exists(version_path):
                with open(version_path, "r") as f:
                    version = f.read().strip()
        except Exception:
            pass

        # Verify database connectivity
        database_status = "healthy"
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            database_status = "unhealthy"

        env = current_app.config.get("ENV") or os.environ.get("APP_ENV", "development")
        uptime = time.time() - start_time

        return {
            "success": True,
            "message": "System status check executed successfully",
            "data": {
                "application": (
                    "healthy" if database_status == "healthy" else "degraded"
                ),
                "database": database_status,
                "environment": env,
                "version": version,
                "uptime": round(uptime, 2),
            },
        }

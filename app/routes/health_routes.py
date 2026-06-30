"""OpsForge API Health Routes.

Defines health and status checking endpoints.
"""

import os
import time
from flask_restx import Namespace, Resource
from sqlalchemy import text
from app.extensions import db
from app.schemas.response.threat_response import (
    get_health_status_model,
    get_success_response_model,
    get_failure_response_model,
)

START_TIME = time.time()

ns = Namespace("health", description="System health status operations")

# Register response structures
health_status_model = get_health_status_model(ns)
success_health_response = get_success_response_model(ns, health_status_model)
failure_response = get_failure_response_model(ns)


def get_app_version() -> str:
    """Reads the application version from the root VERSION file."""
    try:
        # Check standard relative paths to locate root VERSION file
        for path in ["VERSION", "../VERSION", "../../VERSION"]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
    except Exception:
        pass
    return "0.1.0"


@ns.route("")
class HealthResource(Resource):
    """Resource class handling the /health endpoint."""

    @ns.doc("check_health")
    @ns.response(
        200, "System status check executed successfully", success_health_response
    )
    @ns.response(500, "System status check degraded", success_health_response)
    def get(self):
        """Checks API server and database connection health."""
        db_status = "healthy"
        overall_success = True
        status_code = 200

        try:
            db.session.execute(text("SELECT 1"))
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"
            overall_success = False
            status_code = 500

        uptime = time.time() - START_TIME

        return {
            "success": overall_success,
            "message": "System status check executed successfully",
            "data": {
                "application": "healthy",
                "database": db_status,
                "version": get_app_version(),
                "uptime": round(uptime, 2),
                "environment": os.environ.get("APP_ENV", "development"),
            },
        }, status_code

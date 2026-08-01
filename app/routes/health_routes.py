"""OpsForge Health Endpoint Route.

Defines the health check namespace and database connectivity validation.
"""

import time

from flask_restx import Namespace, Resource, fields
from sqlalchemy import text

from app.extensions import db

# Namespace definition
ns = Namespace("health", description="System health and telemetry check")

# Record start time for uptime tracking
start_time = time.time()

health_live_model = ns.model("HealthLive", {"status": fields.String(example="healthy")})

health_ready_model = ns.model(
    "HealthReady",
    {
        "status": fields.String(example="healthy"),
        "database": fields.String(example="connected"),
    },
)


@ns.route("/live")
class HealthLiveResource(Resource):
    @ns.doc("check_live", description="Checks if the application process is running")
    @ns.marshal_with(health_live_model, code=200)
    def get(self) -> dict:
        return {"status": "healthy"}


@ns.route("/ready")
class HealthReadyResource(Resource):
    @ns.doc("check_ready", description="Checks if database is connected and ready")
    @ns.marshal_with(health_ready_model)
    def get(self) -> dict:
        database_status = "connected"
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            database_status = "disconnected"

        status = "healthy" if database_status == "connected" else "unhealthy"

        # We return a 503 if it's not ready so load balancers know
        response_code = 200 if status == "healthy" else 503

        return {"status": status, "database": database_status}, response_code


@ns.route("")
class HealthLegacyResource(Resource):
    @ns.doc("check_health_legacy")
    def get(self) -> dict:
        # Keep old endpoint for backwards compatibility
        return HealthReadyResource().get()

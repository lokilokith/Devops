"""OpsForge API Stats Routes.

Defines statistics and telemetry endpoints.
"""

from flask_restx import Namespace, Resource
from app.services.threat_service import ThreatService
from app.schemas.response.threat_response import (
    get_threat_stats_model,
    get_success_response_model,
    get_failure_response_model,
)

ns = Namespace("stats", description="Threat intelligence aggregate metrics operations")

# Register response structures on this namespace
stats_data_model = get_threat_stats_model(ns)
success_stats_response = get_success_response_model(ns, stats_data_model)
failure_response = get_failure_response_model(ns)


@ns.route("")
class ThreatStatsResource(Resource):
    """Resource class handling the /threats/stats endpoint."""

    @ns.doc("get_threat_stats")
    @ns.response(
        200, "Global metric tallies calculated successfully", success_stats_response
    )
    @ns.response(500, "Internal Server Error", failure_response)
    def get(self):
        """Calculates global threat statistics and metric tallies."""
        stats = ThreatService.get_stats()
        return {
            "success": True,
            "message": "Global metric tallies calculated successfully",
            "data": stats,
        }, 200

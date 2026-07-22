"""OpsForge Statistics Route.

Defines the statistics telemetry endpoints using ThreatService.
"""

from flask_restx import Namespace, Resource, fields

from app.threat.service import ThreatService

ns = Namespace("stats", description="Threat intelligence aggregates and tallies")

# Swagger models
counts_model = ns.model(
    "TypeCounts",
    {
        "ip": fields.Integer(description="Total IP indicators", example=10),
        "domain": fields.Integer(description="Total domain indicators", example=5),
        "hash": fields.Integer(description="Total file hash indicators", example=8),
        "url": fields.Integer(description="Total URL indicators", example=12),
    },
)

stats_data_model = ns.model(
    "StatsData",
    {
        "total_threats": fields.Integer(
            description="Grand total of threat indicators", example=35
        ),
        "critical": fields.Integer(description="Critical severity count", example=2),
        "high": fields.Integer(description="High severity count", example=5),
        "medium": fields.Integer(description="Medium severity count", example=15),
        "low": fields.Integer(description="Low severity count", example=13),
        "open": fields.Integer(description="Open status count", example=10),
        "investigating": fields.Integer(
            description="Investigating status count", example=12
        ),
        "contained": fields.Integer(description="Contained status count", example=8),
        "closed": fields.Integer(description="Closed status count", example=4),
        "false_positive": fields.Integer(
            description="False positive status count", example=1
        ),
        "indicator_type_counts": fields.Nested(counts_model),
        "last_updated": fields.String(
            description="Most recent change timestamp in ISO format",
            example="2026-07-01T15:00:00+00:00",
        ),
    },
)

stats_response_model = ns.model(
    "StatsResponse",
    {
        "success": fields.Boolean(description="Indicates success status", example=True),
        "message": fields.String(
            description="Operation feedback message",
            example="Global metrics calculated successfully",
        ),
        "data": fields.Nested(stats_data_model),
    },
)


@ns.route("")
class StatsResource(Resource):
    """Resource managing global threat metadata statistics tallies."""

    @ns.doc(
        "get_stats",
        description="Aggregates counts by threat level, status, type and last modified",
    )
    @ns.marshal_with(stats_response_model, code=200)
    def get(self) -> dict:
        """Retrieves global telemetry and counts."""
        stats = ThreatService.get_statistics()
        return {
            "success": True,
            "message": "Global metrics calculated successfully",
            "data": stats,
        }


"""OpsForge Threat Request Schemas.

Defines schemas and parser models for incoming requests.
"""

from flask_restx import Namespace, fields, reqparse
from app.constants import THREAT_LEVELS, THREAT_STATUSES, INDICATOR_TYPES


def get_threat_query_parser() -> reqparse.RequestParser:
    """Returns the request parser for threats query parameters."""
    parser = reqparse.RequestParser()
    parser.add_argument("page", type=int, default=1, help="Page number (default: 1)")
    parser.add_argument(
        "limit", type=int, default=20, help="Items per page (default: 20)"
    )
    parser.add_argument(
        "sort", type=str, default="created_at", help="Sort column (default: created_at)"
    )
    parser.add_argument(
        "order",
        type=str,
        default="desc",
        choices=["asc", "desc"],
        help="Sort order (default: desc)",
    )
    parser.add_argument("status", type=str, help="Filter by threat status")
    parser.add_argument("indicator_type", type=str, help="Filter by indicator type")
    return parser


def get_threat_input_model(ns: Namespace) -> fields.Raw:
    """Returns the input model schema for creating or updating a threat."""
    return ns.model(
        "ThreatInput",
        {
            "indicator": fields.String(
                required=True,
                description="The threat indicator (e.g. IP, domain, hash, URL)",
            ),
            "indicator_type": fields.String(
                required=True, enum=INDICATOR_TYPES, description="Type of indicator"
            ),
            "threat_level": fields.String(
                required=True, enum=THREAT_LEVELS, description="Threat severity level"
            ),
            "confidence": fields.Integer(
                required=True, description="Analyst confidence score (0-100)"
            ),
            "mitre_attack": fields.String(
                description="MITRE ATT&CK technique reference (e.g. T1059)"
            ),
            "source": fields.String(
                required=True, description="Source of the threat intelligence"
            ),
            "analyst_notes": fields.String(
                description="Notes from the security analyst"
            ),
            "assigned_analyst": fields.String(
                description="Username of the assigned analyst"
            ),
            "status": fields.String(
                enum=THREAT_STATUSES,
                default="Open",
                description="Threat lifecycle status",
            ),
            "tags": fields.List(
                fields.String, description="List of classification tags"
            ),
            "first_seen": fields.String(
                description="ISO timestamp when the indicator was first seen"
            ),
            "last_seen": fields.String(
                description="ISO timestamp when the indicator was last seen"
            ),
        },
    )


def get_threat_status_model(ns: Namespace) -> fields.Raw:
    """Returns the input model schema for updating threat status."""
    return ns.model(
        "ThreatStatusUpdate",
        {
            "status": fields.String(
                required=True, enum=THREAT_STATUSES, description="New threat status"
            ),
            "last_updated_by": fields.String(
                description="Username of the analyst performing this update"
            ),
        },
    )

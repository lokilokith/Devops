"""OpsForge Threat Response Schemas.

Defines schemas and serializers for outgoing API responses.
"""

from flask_restx import Namespace, fields
from app.constants import THREAT_LEVELS, THREAT_STATUSES, INDICATOR_TYPES


def get_threat_model(ns: Namespace) -> fields.Raw:
    """Returns the Threat representation model for serialization."""
    return ns.model(
        "ThreatResponse",
        {
            "id": fields.Integer(description="The threat unique identifier"),
            "indicator": fields.String(
                description="The threat indicator (e.g. IP, domain, hash, URL)"
            ),
            "indicator_type": fields.String(
                enum=INDICATOR_TYPES, description="Type of indicator"
            ),
            "threat_level": fields.String(
                enum=THREAT_LEVELS, description="Threat severity level"
            ),
            "confidence": fields.Integer(
                description="Analyst confidence score (0-100)"
            ),
            "mitre_attack": fields.String(
                description="MITRE ATT&CK technique reference (e.g. T1059)"
            ),
            "source": fields.String(description="Source of the threat intelligence"),
            "analyst_notes": fields.String(
                description="Notes from the security analyst"
            ),
            "assigned_analyst": fields.String(
                description="Username of the assigned analyst"
            ),
            "last_updated_by": fields.String(
                description="Username of the last analyst who updated the record"
            ),
            "status": fields.String(
                enum=THREAT_STATUSES, description="Threat lifecycle status"
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
            "created_at": fields.String(
                description="Timestamp when this record was created"
            ),
            "updated_at": fields.String(
                description="Timestamp when this record was last updated"
            ),
        },
    )


def get_success_response_model(ns: Namespace, data_fields: fields.Raw) -> fields.Raw:
    """Wraps a model in the standard success format container."""
    model_name = (
        f"Success_{data_fields.name}"
        if hasattr(data_fields, "name")
        else "SuccessResponseGeneric"
    )
    return ns.model(
        model_name,
        {
            "success": fields.Boolean(
                default=True, description="Indicates if operation succeeded"
            ),
            "message": fields.String(description="Operational success summary message"),
            "data": fields.Nested(data_fields),
        },
    )


def get_failure_response_model(ns: Namespace) -> fields.Raw:
    """Returns the uniform failure response schema."""
    return ns.model(
        "FailureResponse",
        {
            "success": fields.Boolean(
                default=False, description="Indicates if operation failed"
            ),
            "message": fields.String(
                description="Validation or structural failure description"
            ),
            "errors": fields.List(
                fields.String, description="List of detailed error description traces"
            ),
        },
    )


def get_paginated_threat_data_model(
    ns: Namespace, threat_model: fields.Raw
) -> fields.Raw:
    """Returns the paginated data structure containing items and page metadata."""
    return ns.model(
        "PaginatedThreatData",
        {
            "items": fields.List(
                fields.Nested(threat_model),
                description="List of threats on the current page",
            ),
            "page": fields.Integer(description="Current page number"),
            "limit": fields.Integer(description="Items per page"),
            "total": fields.Integer(
                description="Total number of items matching filters"
            ),
            "pages": fields.Integer(description="Total number of pages available"),
        },
    )


def get_threat_stats_model(ns: Namespace) -> fields.Raw:
    """Returns the threat metrics model schema."""
    indicator_types_model = ns.model(
        "ThreatStatsIndicatorTypes",
        {
            "ip": fields.Integer(description="Number of IP threat indicators"),
            "domain": fields.Integer(description="Number of domain threat indicators"),
            "hash": fields.Integer(description="Number of hash threat indicators"),
            "url": fields.Integer(description="Number of URL threat indicators"),
        },
    )

    return ns.model(
        "ThreatStats",
        {
            "total": fields.Integer(description="Total count of threat records"),
            "critical": fields.Integer(
                description="Count of critical threat level records"
            ),
            "high": fields.Integer(description="Count of high threat level records"),
            "open": fields.Integer(description="Count of open status records"),
            "closed": fields.Integer(description="Count of closed status records"),
            "last_updated": fields.String(
                description="ISO timestamp of the most recently updated threat record"
            ),
            "indicator_types": fields.Nested(
                indicator_types_model, description="Breakdown of indicators by type"
            ),
        },
    )


def get_health_status_model(ns: Namespace) -> fields.Raw:
    """Returns the application health status model schema."""
    return ns.model(
        "HealthStatus",
        {
            "application": fields.String(
                description="Vitality status of the API instance"
            ),
            "database": fields.String(
                description="Vitality status of the database connection"
            ),
            "version": fields.String(description="Current application version"),
            "uptime": fields.Float(description="Application uptime in seconds"),
            "environment": fields.String(
                description="Active environment setting (APP_ENV)"
            ),
        },
    )

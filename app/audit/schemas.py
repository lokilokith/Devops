"""Audit DTO Schemas."""

from __future__ import annotations

from flask_restx import Namespace, fields

audit_ns = Namespace("audit", description="Audit operations")

audit_log_response_dto = audit_ns.model(
    "AuditLogResponse",
    {
        "id": fields.String(description="Log UUID"),
        "event_id": fields.String(description="Event unique ID", attribute="event_id"),
        "user_id": fields.String(description="Actor User UUID", attribute="actor_user_id"),
        "target_user_id": fields.String(description="Target User UUID"),
        "action": fields.String(description="Action performed"),
        "resource_type": fields.String(description="Resource type"),
        "resource_id": fields.String(description="Resource ID"),
        "status": fields.String(description="Outcome status"),
        "severity": fields.String(description="Event severity"),
        "details": fields.Raw(description="Additional details"),
        "created_at": fields.DateTime(description="Timestamp", attribute="timestamp"),
    },
)

audit_log_paginated_response_dto = audit_ns.model(
    "AuditLogPaginatedResponse",
    {
        "items": fields.List(fields.Nested(audit_log_response_dto)),
        "total": fields.Integer(description="Total count of logs matching query"),
    },
)

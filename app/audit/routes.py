"""Audit API Routes."""

from __future__ import annotations

from flask import request
from flask_restx import Resource

from app.api.decorators import login_required
from app.api.responses import success_response
from app.audit.schemas import (
    audit_log_paginated_response_dto,
    audit_log_paginated_wrapper,
    audit_ns,
)
from app.extensions import db
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from flask_restx import marshal

def get_audit_service() -> AuditService:
    return AuditService(AuditRepository(db.session))

@audit_ns.route("")
class AuditCollection(Resource):
    @audit_ns.marshal_with(audit_log_paginated_wrapper)
    @login_required
    def get(self):
        """List audit logs."""
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        
        filters = {}
        if resource_type := request.args.get("resource_type"):
            filters["resource_type"] = resource_type
        if action := request.args.get("action"):
            filters["action"] = action
        if status := request.args.get("status"):
            filters["status"] = status
        if severity := request.args.get("severity"):
            filters["severity"] = severity
            
        service = get_audit_service()
        items = service.search_logs(page=page, page_size=per_page, **filters)
        total = service.count_logs(**filters)
        
        data_resp = marshal({
            "items": items,
            "total": total
        }, audit_log_paginated_response_dto)
        return success_response(data=data_resp, status_code=200)

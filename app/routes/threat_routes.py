"""OpsForge API Threat Routes.

Defines CRUD and workflow endpoints for Threat intelligence indicators.
"""

from flask import request
from flask_restx import Namespace, Resource
from app.services.threat_service import ThreatService
from app.schemas.request.threat_request import (
    get_threat_input_model,
    get_threat_status_model,
    get_threat_query_parser,
)
from app.schemas.response.threat_response import (
    get_threat_model,
    get_success_response_model,
    get_failure_response_model,
    get_paginated_threat_data_model,
)

ns = Namespace("threats", description="Threat Intelligence Management operations")

# Load models and parsers on Namespace
threat_input = get_threat_input_model(ns)
threat_status = get_threat_status_model(ns)
query_parser = get_threat_query_parser()

threat_resp = get_threat_model(ns)
success_single = get_success_response_model(ns, threat_resp)
success_paginated = get_success_response_model(
    ns, get_paginated_threat_data_model(ns, threat_resp)
)
failure_resp = get_failure_response_model(ns)


@ns.route("")
class ThreatListResource(Resource):
    """Resource handling threat collection operations (list and create)."""

    @ns.doc("list_threats")
    @ns.expect(query_parser)
    @ns.response(200, "Threats retrieved successfully", success_paginated)
    @ns.response(400, "Validation Error", failure_resp)
    def get(self):
        """List all threat indicators with optional filtering, sorting, and pagination."""
        args = query_parser.parse_args()

        pagination_params = {
            "page": args.get("page", 1),
            "limit": args.get("limit", 20),
            "sort": args.get("sort", "created_at"),
            "order": args.get("order", "desc"),
        }

        filter_params = {
            "status": args.get("status"),
            "indicator_type": args.get("indicator_type"),
        }

        pagination_obj = ThreatService.get_threats(pagination_params, filter_params)

        return {
            "success": True,
            "message": "Threats retrieved successfully",
            "data": {
                "items": [t.to_dict() for t in pagination_obj.items],
                "page": pagination_obj.page,
                "limit": pagination_obj.per_page,
                "total": pagination_obj.total,
                "pages": pagination_obj.pages,
            },
        }, 200

    @ns.doc("create_threat")
    @ns.expect(threat_input, validate=True)
    @ns.response(201, "Threat created successfully", success_single)
    @ns.response(400, "Validation Error", failure_resp)
    def post(self):
        """Create a new threat intelligence indicator."""
        data = request.json
        threat = ThreatService.create_threat(data)
        return {
            "success": True,
            "message": "Threat created successfully",
            "data": threat.to_dict(),
        }, 201


@ns.route("/<int:id>")
@ns.param("id", "The threat unique identifier")
class ThreatDetailResource(Resource):
    """Resource handling individual threat details (read, update, delete)."""

    @ns.doc("get_threat")
    @ns.response(200, "Threat retrieved successfully", success_single)
    @ns.response(404, "Threat not found", failure_resp)
    def get(self, id):
        """Get a threat indicator by ID."""
        threat = ThreatService.get_threat_by_id(id)
        return {
            "success": True,
            "message": "Threat retrieved successfully",
            "data": threat.to_dict(),
        }, 200

    @ns.doc("update_threat")
    @ns.expect(threat_input, validate=True)
    @ns.response(200, "Threat updated successfully", success_single)
    @ns.response(400, "Validation Error", failure_resp)
    @ns.response(404, "Threat not found", failure_resp)
    def put(self, id):
        """Update an existing threat indicator."""
        data = request.json
        threat = ThreatService.update_threat(id, data)
        return {
            "success": True,
            "message": "Threat updated successfully",
            "data": threat.to_dict(),
        }, 200

    @ns.doc("delete_threat")
    @ns.response(200, "Threat deleted successfully", success_single)
    @ns.response(404, "Threat not found", failure_resp)
    def delete(self, id):
        """Delete a threat indicator."""
        ThreatService.delete_threat(id)
        return {
            "success": True,
            "message": f"Threat with ID {id} deleted successfully",
            "data": {},
        }, 200


@ns.route("/<int:id>/status")
@ns.param("id", "The threat unique identifier")
class ThreatStatusUpdateResource(Resource):
    """Resource handling status transitions for a threat indicator."""

    @ns.doc("update_threat_status")
    @ns.expect(threat_status, validate=True)
    @ns.response(200, "Threat status updated successfully", success_single)
    @ns.response(400, "Validation Error", failure_resp)
    @ns.response(404, "Threat not found", failure_resp)
    def patch(self, id):
        """Partially update a threat indicator's status using state machine rules."""
        data = request.json
        status = data.get("status")
        last_updated_by = data.get("last_updated_by")
        threat = ThreatService.update_threat_status(id, status, last_updated_by)
        return {
            "success": True,
            "message": "Threat status updated successfully",
            "data": threat.to_dict(),
        }, 200

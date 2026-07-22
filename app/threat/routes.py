"""OpsForge Threat Intelligence Namespace Routes.

Exposes CRUD, search, pagination, and status changes for threat indicators.
"""

from flask import request
from flask_restx import Namespace, Resource, fields, reqparse

from app.constants import INDICATOR_TYPES, THREAT_LEVELS, THREAT_STATUSES
from app.threat.service import ThreatService

ns = Namespace("threats", description="Threat intelligence indicator management")

# Reusable models
threat_model = ns.model(
    "ThreatIndicator",
    {
        "id": fields.Integer(
            readOnly=True, description="Unique database ID", example=1
        ),
        "indicator": fields.String(
            required=True,
            description="The threat indicator pattern (IP, Domain, URL, Hash)",
            example="1.1.1.1",
        ),
        "indicator_type": fields.String(
            required=True,
            description="Type of the indicator",
            enum=INDICATOR_TYPES,
            example="ip",
        ),
        "threat_level": fields.String(
            required=True,
            description="Severity rating",
            enum=THREAT_LEVELS,
            example="critical",
        ),
        "confidence": fields.Integer(
            required=True, description="Trust percentage", min=0, max=100, example=90
        ),
        "mitre_attack": fields.String(
            description="MITRE ATT&CK reference ID", example="T1078"
        ),
        "source": fields.String(
            required=True,
            description="Reporting threat intel feed or analyst unit",
            example="alienvault",
        ),
        "analyst_notes": fields.String(
            description="Operational comments",
            example="Observed command and control traffic",
        ),
        "assigned_analyst": fields.String(
            description="Username of assigned responder", example="analyst_alice"
        ),
        "status": fields.String(
            description="Workflow status", enum=THREAT_STATUSES, example="Open"
        ),
        "tags": fields.List(
            fields.String,
            description="Classification tags",
            example=["phishing", "malware"],
        ),
        "first_seen": fields.String(
            description="First seen datetime in ISO format",
            example="2026-07-01T10:00:00Z",
        ),
        "last_seen": fields.String(
            description="Last seen datetime in ISO format",
            example="2026-07-01T15:00:00Z",
        ),
        "created_at": fields.String(
            readOnly=True,
            description="Timestamp of record creation",
            example="2026-07-01T15:00:00Z",
        ),
        "updated_at": fields.String(
            readOnly=True,
            description="Timestamp of last update",
            example="2026-07-01T15:05:00Z",
        ),
    },
)

# Response Wrappers
threat_response = ns.model(
    "ThreatResponse",
    {
        "success": fields.Boolean(description="Indicates success status", example=True),
        "message": fields.String(
            description="Feedback message", example="Threat created successfully"
        ),
        "data": fields.Nested(threat_model),
    },
)

threat_list_data = ns.model(
    "ThreatListData",
    {
        "items": fields.List(fields.Nested(threat_model)),
        "page": fields.Integer(description="Current page number", example=1),
        "limit": fields.Integer(description="Limit of items per page", example=20),
        "total": fields.Integer(
            description="Grand total of threat records", example=35
        ),
        "pages": fields.Integer(description="Grand total of pages", example=2),
    },
)

threat_list_response = ns.model(
    "ThreatListResponse",
    {
        "success": fields.Boolean(description="Indicates success status", example=True),
        "message": fields.String(
            description="Feedback message", example="Threats retrieved successfully"
        ),
        "data": fields.Nested(threat_list_data),
    },
)

generic_response = ns.model(
    "GenericResponse",
    {
        "success": fields.Boolean(description="Indicates success status", example=True),
        "message": fields.String(
            description="Feedback message", example="Threat deleted successfully"
        ),
        "data": fields.Raw(description="Empty data context placeholder", example={}),
    },
)

# Input models
status_update_model = ns.model(
    "StatusUpdatePayload",
    {
        "status": fields.String(
            required=True,
            description="New workflow status",
            enum=THREAT_STATUSES,
            example="Investigating",
        ),
        "assigned_analyst": fields.String(
            description="Username of assigned analyst", example="analyst_bob"
        ),
    },
)

# Query Parsers
list_parser = reqparse.RequestParser()
list_parser.add_argument(
    "status", type=str, required=False, help="Filter by threat status"
)
list_parser.add_argument(
    "indicator_type", type=str, required=False, help="Filter by type"
)
list_parser.add_argument(
    "page", type=int, default=1, required=False, help="Page offset"
)
list_parser.add_argument(
    "limit", type=int, default=20, required=False, help="Page limit"
)
list_parser.add_argument(
    "sort", type=str, default="created_at", required=False, help="Sorting column key"
)
list_parser.add_argument(
    "order",
    type=str,
    default="desc",
    required=False,
    help="Order of sorting (asc/desc)",
)

search_parser = reqparse.RequestParser()
search_parser.add_argument(
    "query",
    type=str,
    required=True,
    help="Partial match query string matching indicator or source",
)


@ns.route("")
class ThreatListResource(Resource):
    """Resource managing bulk operations and pagination queries for threats."""

    @ns.doc(
        "list_threats", description="Fetches windowed pagination query of indicators"
    )
    @ns.expect(list_parser)
    @ns.marshal_with(threat_list_response, code=200)
    def get(self) -> dict:
        """Retrieves filtering paginated threat indexes."""
        args = list_parser.parse_args()
        filters = {}
        if args.get("status"):
            filters["status"] = args["status"]
        if args.get("indicator_type"):
            filters["indicator_type"] = args["indicator_type"]

        pagination = ThreatService.list_threats(
            filters=filters,
            page=args["page"],
            limit=args["limit"],
            sort=args["sort"],
            order=args["order"],
        )

        return {
            "success": True,
            "message": "Threats retrieved successfully",
            "data": {
                "items": [item.to_dict() for item in pagination.items],
                "page": pagination.page,
                "limit": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }

    @ns.doc("create_threat", description="Inserts a new validated threat indicator")
    @ns.expect(threat_model, validate=True)
    @ns.marshal_with(threat_response, code=201)
    def post(self) -> tuple[dict, int]:
        """Creates a threat record."""
        payload = request.json
        threat = ThreatService.create_threat(payload)
        return {
            "success": True,
            "message": "Threat created successfully",
            "data": threat.to_dict(),
        }, 201


@ns.route("/search")
class ThreatSearchResource(Resource):
    """Resource managing text search capabilities on indicators."""

    @ns.doc(
        "search_threats",
        description="Queries threats by partial match on indicator or source",
    )
    @ns.expect(search_parser)
    @ns.marshal_with(threat_list_response, code=200)
    def get(self) -> dict:
        """Searches threat intelligence records."""
        args = search_parser.parse_args()
        results = ThreatService.search_threats(args["query"])
        return {
            "success": True,
            "message": "Search results retrieved successfully",
            "data": {
                "items": [item.to_dict() for item in results],
                "page": 1,
                "limit": len(results),
                "total": len(results),
                "pages": 1,
            },
        }


@ns.route("/<int:threat_id>")
@ns.param("threat_id", "Unique database primary key identifier")
class ThreatDetailResource(Resource):
    """Manage read, update, and delete for specific threats."""

    @ns.doc(
        "get_threat",
        description="Fetches a single threat indicator by database primary key ID",
    )
    @ns.marshal_with(threat_response, code=200)
    def get(self, threat_id: int) -> dict:
        """Reads a specific threat record."""
        threat = ThreatService.get_threat(threat_id)
        return {
            "success": True,
            "message": "Threat retrieved successfully",
            "data": threat.to_dict(),
        }

    @ns.doc(
        "update_threat",
        description="Overwrites all fields of an existing threat indicator",
    )
    @ns.expect(threat_model, validate=True)
    @ns.marshal_with(threat_response, code=200)
    def put(self, threat_id: int) -> dict:
        """Modifies a specific threat record."""
        payload = request.json
        threat = ThreatService.update_threat(threat_id, payload)
        return {
            "success": True,
            "message": "Threat updated successfully",
            "data": threat.to_dict(),
        }

    @ns.doc(
        "delete_threat", description="Purges a threat indicator from database storage"
    )
    @ns.marshal_with(generic_response, code=200)
    def delete(self, threat_id: int) -> dict:
        """Deletes a specific threat record."""
        ThreatService.delete_threat(threat_id)
        return {
            "success": True,
            "message": f"Threat with ID {threat_id} deleted successfully",
            "data": {},
        }


@ns.route("/<int:threat_id>/status")
@ns.param("threat_id", "Unique database primary key identifier")
class ThreatStatusResource(Resource):
    """Resource managing status state transitions and assignments."""

    @ns.doc(
        "change_status",
        description="Validates and applies a status change state transition",
    )
    @ns.expect(status_update_model, validate=True)
    @ns.marshal_with(threat_response, code=200)
    def patch(self, threat_id: int) -> dict:
        """Updates the status of a threat record."""
        payload = request.json
        threat = ThreatService.change_status(
            threat_id=threat_id,
            new_status=payload["status"],
            analyst_name=payload.get("assigned_analyst"),
        )
        return {
            "success": True,
            "message": "Threat status updated successfully",
            "data": threat.to_dict(),
        }


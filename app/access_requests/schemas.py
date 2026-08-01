"""AccessRequest schemas for serialization/deserialization."""

from flask_restx import Namespace, fields

access_requests_ns = Namespace(
    "access-requests", description="Access Requests operations"
)

access_request_create_model = access_requests_ns.model(
    "AccessRequestCreate",
    {
        "requested_role_id": fields.String(
            description="UUID of requested role", required=False
        ),
        "requested_resource_id": fields.String(
            description="UUID of requested resource", required=False
        ),
        "business_justification": fields.String(
            description="Reason for access", required=True
        ),
        "priority": fields.String(
            description="Priority (low, medium, high, critical)", required=False
        ),
        "requested_start": fields.DateTime(
            description="Requested start time", required=False
        ),
        "requested_end": fields.DateTime(
            description="Requested end time", required=False
        ),
    },
)

access_request_reject_model = access_requests_ns.model(
    "AccessRequestReject",
    {
        "rejected_reason": fields.String(
            description="Reason for rejection", required=True
        )
    },
)


class EnumField(fields.String):
    def format(self, value):
        if hasattr(value, "value"):
            return value.value
        return str(value)


access_request_response_model = access_requests_ns.model(
    "AccessRequestResponse",
    {
        "id": fields.String(description="UUID of request"),
        "request_number": fields.String(description="Human readable request number"),
        "requester_id": fields.String(description="UUID of requester"),
        "requested_role_id": fields.String(description="UUID of requested role"),
        "requested_resource_id": fields.String(
            description="UUID of requested resource"
        ),
        "business_justification": fields.String(description="Reason for access"),
        "status": EnumField(description="Current status of the request"),
        "priority": EnumField(description="Priority"),
        "requested_start": fields.DateTime(description="Requested start time"),
        "requested_end": fields.DateTime(description="Requested end time"),
        "approved_by": fields.String(description="UUID of approver"),
        "approved_at": fields.DateTime(description="Approval time"),
        "rejected_reason": fields.String(description="Reason for rejection"),
        "created_at": fields.DateTime(description="Creation time"),
        "updated_at": fields.DateTime(description="Update time"),
    },
)

access_requests_list_response_model = access_requests_ns.model(
    "AccessRequestsListResponse",
    {
        "success": fields.Boolean(default=True),
        "message": fields.String(default="Success"),
        "data": fields.List(fields.Nested(access_request_response_model)),
        "meta": fields.Raw(description="Pagination metadata"),
    },
)

access_request_single_response_model = access_requests_ns.model(
    "AccessRequestSingleResponse",
    {
        "success": fields.Boolean(default=True),
        "message": fields.String(default="Success"),
        "data": fields.Nested(access_request_response_model),
        "meta": fields.Raw(default={}),
    },
)

"""ApprovalWorkflow schemas for serialization/deserialization."""
from flask_restx import Namespace, fields

approval_workflows_ns = Namespace("approval-workflows", description="Approval Workflows operations")

class EnumField(fields.String):
    """Custom String field that extracts the .value from Enums."""
    def format(self, value):
        if hasattr(value, "value"):
            return value.value
        return str(value)

approval_workflow_response_model = approval_workflows_ns.model("ApprovalWorkflowResponse", {
    "id": fields.String(description="UUID of workflow"),
    "access_request_id": fields.String(description="UUID of associated access request"),
    "approver_id": fields.String(description="UUID of approver"),
    "approval_level": EnumField(description="Approval level required"),
    "status": EnumField(description="Current status of the workflow"),
    "comments": fields.String(description="Optional comments left by approver"),
    "approved_at": fields.DateTime(description="Time of approval"),
    "created_at": fields.DateTime(description="Creation time"),
    "updated_at": fields.DateTime(description="Update time"),
})

approval_workflow_list_response_model = approval_workflows_ns.model("ApprovalWorkflowListResponse", {
    "success": fields.Boolean(default=True),
    "message": fields.String(default="Success"),
    "data": fields.List(fields.Nested(approval_workflow_response_model)),
    "meta": fields.Raw(description="Pagination metadata")
})

approval_workflow_single_response_model = approval_workflows_ns.model("ApprovalWorkflowSingleResponse", {
    "success": fields.Boolean(default=True),
    "message": fields.String(default="Success"),
    "data": fields.Nested(approval_workflow_response_model),
    "meta": fields.Raw(default={})
})

approval_action_model = approval_workflows_ns.model("ApprovalAction", {
    "comments": fields.String(description="Optional justification/comment", required=False)
})

# Request Parsers for Filtering & Pagination
approval_workflow_query_parser = approval_workflows_ns.parser()
approval_workflow_query_parser.add_argument("page", type=int, required=False, default=1, help="Page number")
approval_workflow_query_parser.add_argument("page_size", type=int, required=False, default=50, help="Items per page")
approval_workflow_query_parser.add_argument("status", type=str, required=False, help="Filter by status (pending, approved, rejected, cancelled)")
approval_workflow_query_parser.add_argument("request_id", type=str, required=False, help="Filter by access request ID")
approval_workflow_query_parser.add_argument("approver_id", type=str, required=False, help="Filter by approver ID")
approval_workflow_query_parser.add_argument("created_after", type=str, required=False, help="Filter by creation time (ISO 8601)")
approval_workflow_query_parser.add_argument("created_before", type=str, required=False, help="Filter by creation time (ISO 8601)")

__all__ = [
    "approval_workflows_ns",
    "approval_workflow_response_model",
    "approval_workflow_list_response_model",
    "approval_workflow_single_response_model",
    "approval_action_model",
    "approval_workflow_query_parser"
]

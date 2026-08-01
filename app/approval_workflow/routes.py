"""ApprovalWorkflow REST API Routes."""

from datetime import datetime
from uuid import UUID

from flask import g, request
from flask_restx import Resource
from werkzeug.exceptions import Conflict, NotFound, UnprocessableEntity

from app.api.decorators import login_required
from app.approval_workflow.exceptions import (
    ApprovalWorkflowInvalidStateError,
    ApprovalWorkflowValidationError,
)
from app.approval_workflow.models import (  # noqa: F401 — registers table in db.metadata for Alembic
    ApprovalWorkflow,
)
from app.approval_workflow.schemas import (
    approval_action_model,
    approval_workflow_list_response_model,
    approval_workflow_query_parser,
    approval_workflow_single_response_model,
    approval_workflows_ns,
)


# Locator pattern function to fetch the service
def get_service():
    from app.access_requests.repository import AccessRequestRepository
    from app.approval_workflow.repository import ApprovalWorkflowRepository
    from app.approval_workflow.service import ApprovalWorkflowService
    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.platform.extensions import db
    from app.user_roles.repository import UserRolesRepository

    return ApprovalWorkflowService(
        ApprovalWorkflowRepository(db.session),
        AccessRequestRepository(db.session),
        UserRolesRepository(db.session),
        AuditService(AuditRepository(db.session)),
        db.session,
    )


@approval_workflows_ns.route("")
class ApprovalWorkflowCollection(Resource):
    @approval_workflows_ns.doc("list_approval_workflows")
    @approval_workflows_ns.expect(approval_workflow_query_parser)
    @approval_workflows_ns.response(
        200, "Success", approval_workflow_list_response_model
    )
    @approval_workflows_ns.response(401, "Unauthorized")
    @approval_workflows_ns.response(403, "Forbidden")
    @approval_workflows_ns.marshal_with(approval_workflow_list_response_model)
    @login_required
    def get(self):
        """List and filter approval workflows."""
        args = approval_workflow_query_parser.parse_args()

        created_after = None
        if args.get("created_after"):
            try:
                created_after = datetime.fromisoformat(
                    args["created_after"].replace("Z", "+00:00")
                )
            except ValueError:
                raise UnprocessableEntity("Invalid created_after date format.")

        created_before = None
        if args.get("created_before"):
            try:
                created_before = datetime.fromisoformat(
                    args["created_before"].replace("Z", "+00:00")
                )
            except ValueError:
                raise UnprocessableEntity("Invalid created_before date format.")

        svc = get_service()

        try:
            items, total = svc.list_workflows(
                current_user_id=UUID(g.user_id),
                page=args["page"],
                page_size=args["page_size"],
                status=args.get("status"),
                request_id=UUID(args["request_id"]) if args.get("request_id") else None,
                approver_id=(
                    UUID(args["approver_id"]) if args.get("approver_id") else None
                ),
                created_after=created_after,
                created_before=created_before,
            )
        except ValueError:
            raise UnprocessableEntity(
                "Invalid UUID format for request_id or approver_id."
            )

        return {
            "success": True,
            "message": "Success",
            "data": items,
            "meta": {
                "page": args["page"],
                "page_size": args["page_size"],
                "total": total,
            },
        }, 200


@approval_workflows_ns.route("/<uuid:workflow_id>")
@approval_workflows_ns.param("workflow_id", "The workflow identifier")
class ApprovalWorkflowResource(Resource):
    @approval_workflows_ns.doc("get_approval_workflow")
    @approval_workflows_ns.response(
        200, "Success", approval_workflow_single_response_model
    )
    @approval_workflows_ns.response(401, "Unauthorized")
    @approval_workflows_ns.response(403, "Forbidden")
    @approval_workflows_ns.response(404, "Not Found")
    @approval_workflows_ns.marshal_with(approval_workflow_single_response_model)
    @login_required
    def get(self, workflow_id):
        """Get an approval workflow by ID."""
        svc = get_service()
        from werkzeug.exceptions import Forbidden

        try:
            wf = svc.get_workflow(
                current_user_id=UUID(g.user_id), workflow_id=workflow_id
            )
        except Forbidden as e:
            raise Forbidden(str(e))
        if not wf:
            raise NotFound(f"Approval workflow {workflow_id} not found.")
        return {"success": True, "message": "Success", "data": wf, "meta": {}}, 200


@approval_workflows_ns.route("/<uuid:workflow_id>/approve")
@approval_workflows_ns.param("workflow_id", "The workflow identifier")
class ApprovalWorkflowApprove(Resource):
    @approval_workflows_ns.doc("approve_workflow")
    @approval_workflows_ns.expect(approval_action_model)
    @approval_workflows_ns.response(
        200, "Success", approval_workflow_single_response_model
    )
    @approval_workflows_ns.response(401, "Unauthorized")
    @approval_workflows_ns.response(403, "Forbidden")
    @approval_workflows_ns.response(404, "Not Found")
    @approval_workflows_ns.response(409, "Invalid State")
    @approval_workflows_ns.response(422, "Validation Error")
    @approval_workflows_ns.marshal_with(approval_workflow_single_response_model)
    @login_required
    def post(self, workflow_id):
        """Approve a workflow request."""
        data = request.json or {}
        comments = data.get("comments")
        svc = get_service()

        try:
            wf = svc.approve(
                workflow_id, approver_id=UUID(g.user_id), comments=comments
            )
            return {
                "success": True,
                "message": "Workflow approved.",
                "data": wf,
                "meta": {},
            }, 200
        except ApprovalWorkflowValidationError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise UnprocessableEntity(str(e))
        except ApprovalWorkflowInvalidStateError as e:
            raise Conflict(str(e))


@approval_workflows_ns.route("/<uuid:workflow_id>/reject")
@approval_workflows_ns.param("workflow_id", "The workflow identifier")
class ApprovalWorkflowReject(Resource):
    @approval_workflows_ns.doc("reject_workflow")
    @approval_workflows_ns.expect(approval_action_model)
    @approval_workflows_ns.response(
        200, "Success", approval_workflow_single_response_model
    )
    @approval_workflows_ns.response(401, "Unauthorized")
    @approval_workflows_ns.response(403, "Forbidden")
    @approval_workflows_ns.response(404, "Not Found")
    @approval_workflows_ns.response(409, "Invalid State")
    @approval_workflows_ns.response(422, "Validation Error")
    @approval_workflows_ns.marshal_with(approval_workflow_single_response_model)
    @login_required
    def post(self, workflow_id):
        """Reject a workflow request."""
        data = request.json or {}
        comments = data.get("comments")
        svc = get_service()

        try:
            wf = svc.reject(workflow_id, rejecter_id=UUID(g.user_id), comments=comments)
            return {
                "success": True,
                "message": "Workflow rejected.",
                "data": wf,
                "meta": {},
            }, 200
        except ApprovalWorkflowValidationError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise UnprocessableEntity(str(e))
        except ApprovalWorkflowInvalidStateError as e:
            raise Conflict(str(e))


@approval_workflows_ns.route("/<uuid:workflow_id>/cancel")
@approval_workflows_ns.param("workflow_id", "The workflow identifier")
class ApprovalWorkflowCancel(Resource):
    @approval_workflows_ns.doc("cancel_workflow")
    @approval_workflows_ns.expect(approval_action_model)
    @approval_workflows_ns.response(
        200, "Success", approval_workflow_single_response_model
    )
    @approval_workflows_ns.response(401, "Unauthorized")
    @approval_workflows_ns.response(403, "Forbidden")
    @approval_workflows_ns.response(404, "Not Found")
    @approval_workflows_ns.response(409, "Invalid State")
    @approval_workflows_ns.response(422, "Validation Error")
    @approval_workflows_ns.marshal_with(approval_workflow_single_response_model)
    @login_required
    def post(self, workflow_id):
        """Cancel a workflow request."""
        data = request.json or {}
        comments = data.get("comments")
        svc = get_service()

        try:
            wf = svc.cancel(
                workflow_id, canceller_id=UUID(g.user_id), comments=comments
            )
            return {
                "success": True,
                "message": "Workflow cancelled.",
                "data": wf,
                "meta": {},
            }, 200
        except ApprovalWorkflowValidationError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise UnprocessableEntity(str(e))
        except ApprovalWorkflowInvalidStateError as e:
            raise Conflict(str(e))

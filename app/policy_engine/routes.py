"""Policy Engine REST API Routes."""

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import Conflict, NotFound

from app.api.decorators import login_required, requires_permission
from app.api.pagination import DEFAULT_PAGE_SIZE, validate_pagination
from app.api.responses import success_response
from app.platform.extensions import db
from app.policy_engine.exceptions import PolicyNotFoundError, PolicyValidationError
from app.policy_engine.repository import PolicyRepository
from app.policy_engine.schemas import (
    policies_ns,
    policy_create_model,
    policy_evaluate_request_model,
    policy_evaluate_response_model,
    policy_list_response_model,
    policy_response_model,
    policy_update_model,
)
from app.policy_engine.service import PolicyService
from app.policy_engine.validators import (
    validate_policy_create,
    validate_policy_update,
    validate_uuid,
)


def get_service() -> PolicyService:
    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.authorization.service import AuthorizationService

    return PolicyService(
        PolicyRepository(db.session),
        AuthorizationService(db.session),
        AuditService(AuditRepository(db.session)),
    )


@policies_ns.route("/policies")
class PolicyCollection(Resource):
    @policies_ns.doc(
        summary="List policies", description="Retrieve a paginated list of policies."
    )
    @policies_ns.marshal_with(policy_list_response_model)
    @login_required
    @requires_permission("policies", "read")
    def get(self):
        skip, limit = validate_pagination(
            request.args.get("skip", 1), request.args.get("limit", DEFAULT_PAGE_SIZE)
        )

        enabled_str = request.args.get("enabled")
        enabled = None
        if enabled_str:
            enabled = enabled_str.lower() in ("true", "1", "yes")

        service = get_service()
        # skip is 'page' logic in our get_service, actually wait.
        # Roles pagination uses skip/limit where skip is offset.
        # In my PolicyService I made page and page_size.
        # Convert skip (offset) back to page if needed, or adjust service list_policies.
        # Actually I can just pass page and page_size.
        page = (skip // limit) + 1 if limit else 1

        policies = service.list_policies(enabled=enabled, page=page, page_size=limit)
        total = service._repo.count_policies(enabled=enabled)

        return success_response(
            data=policies, meta={"total": total, "skip": skip, "limit": limit}
        )

    @policies_ns.doc(summary="Create policy", description="Create a new access policy.")
    @policies_ns.expect(policy_create_model)
    @policies_ns.marshal_with(policy_response_model, code=201)
    @login_required
    @requires_permission("policies", "create")
    def post(self):
        data = request.json or {}
        validate_policy_create(data)
        service = get_service()
        try:
            policy = service.create_policy(data)
            return success_response(
                data=policy, message="Policy created successfully", status_code=201
            )
        except PolicyValidationError as e:
            raise Conflict(str(e))


@policies_ns.route("/policies/<string:policy_id>")
class PolicyResource(Resource):
    @policies_ns.doc(summary="Get policy", description="Retrieve a policy by UUID.")
    @policies_ns.marshal_with(policy_response_model)
    @login_required
    @requires_permission("policies", "read")
    def get(self, policy_id):
        uid = validate_uuid(policy_id)
        service = get_service()
        try:
            policy = service.get_policy(uid)
            return success_response(data=policy)
        except PolicyNotFoundError as e:
            raise NotFound(str(e))

    @policies_ns.doc(summary="Update policy", description="Update a policy by UUID.")
    @policies_ns.expect(policy_update_model)
    @policies_ns.marshal_with(policy_response_model)
    @login_required
    @requires_permission("policies", "update")
    def patch(self, policy_id):
        uid = validate_uuid(policy_id)
        data = request.json or {}
        validate_policy_update(data)
        service = get_service()
        try:
            policy = service.update_policy(uid, data)
            return success_response(data=policy, message="Policy updated successfully")
        except PolicyNotFoundError as e:
            raise NotFound(str(e))
        except PolicyValidationError as e:
            raise Conflict(str(e))

    @policies_ns.doc(summary="Delete policy", description="Delete a policy by UUID.")
    @policies_ns.marshal_with(policy_response_model)
    @login_required
    @requires_permission("policies", "delete")
    def delete(self, policy_id):
        uid = validate_uuid(policy_id)
        service = get_service()
        try:
            service.delete_policy(uid)
            return success_response(message="Policy deleted successfully")
        except PolicyNotFoundError as e:
            raise NotFound(str(e))


@policies_ns.route("/evaluate")
class PolicyEvaluateResource(Resource):
    @policies_ns.doc(
        summary="Evaluate policy",
        description="Simulate/test policy evaluation for a user and resource.",
    )
    @policies_ns.expect(policy_evaluate_request_model)
    @policies_ns.marshal_with(policy_evaluate_response_model)
    @login_required
    @requires_permission("policies", "read")
    def post(self):
        data = request.json or {}
        user_id = validate_uuid(data.get("user_id", ""))
        resource_id = data.get("resource_id", "")
        action = data.get("action", "")
        context = data.get("context", {})

        service = get_service()
        decision = service.evaluate_policy(user_id, resource_id, action, context)

        return success_response(data=decision, message="Evaluation completed")

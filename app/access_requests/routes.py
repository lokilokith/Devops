"""Access requests API routes."""
from uuid import UUID
from flask import request, g
from flask_restx import Resource
from werkzeug.exceptions import BadRequest, Conflict, NotFound, UnprocessableEntity

from app.access_requests.schemas import (
    access_requests_ns,
    access_request_create_model,
    access_request_reject_model,
    access_requests_list_response_model,
    access_request_single_response_model
)
from app.access_requests.validators import validate_access_request_create, validate_pagination
from app.access_requests.service import AccessRequestService
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.exceptions import (
    AccessRequestInvalidStateError,
    AccessRequestDuplicateError,
    AccessRequestValidationError,
    AccessRequestNotFoundError
)
from app.api.decorators import login_required, requires_permission
from app.authorization.service import AuthorizationService
from app.permissions.models import PermissionAction
from app.identity.repository import IdentityRepository
from app.roles.repository import RolesRepository
from app.resources.repository import ResourcesRepository
from app.user_roles.repository import UserRolesRepository
from app.extensions import db

def get_service() -> AccessRequestService:
    return AccessRequestService(
        AccessRequestRepository(db.session),
        IdentityRepository(db.session),
        RolesRepository(db.session),
        ResourcesRepository(db.session),
        UserRolesRepository(db.session)
    )

@access_requests_ns.route("")
class AccessRequestList(Resource):
    @access_requests_ns.doc("list_access_requests")
    @access_requests_ns.param("skip", "Number of records to skip", type=int, default=0)
    @access_requests_ns.param("limit", "Number of records to return", type=int, default=50)
    @access_requests_ns.marshal_with(access_requests_list_response_model)
    @login_required
    def get(self):
        """List access requests."""
        skip, limit = validate_pagination(
            request.args.get("skip", 0),
            request.args.get("limit", 50)
        )
        
        authz = AuthorizationService(db.session)
        is_admin_or_auditor = authz.has_permission(UUID(g.user_id), "access_requests", PermissionAction.READ)
        
        service = get_service()
        
        # Calculate page for internal repo
        page = (skip // limit) + 1 if limit > 0 else 1
        page_size = limit
        
        if is_admin_or_auditor:
            requests = service._repo.list_requests(page=page, page_size=page_size)
            total = service._repo.count()
        else:
            requests = service._repo.search(page=page, page_size=page_size, requester_id=UUID(g.user_id))
            total = service._repo.count(requester_id=UUID(g.user_id))
            
        return {
            "success": True,
            "message": "Access requests retrieved successfully",
            "data": requests,
            "meta": {"skip": skip, "limit": limit, "total": total}
        }

    @access_requests_ns.doc("create_access_request")
    @access_requests_ns.expect(access_request_create_model)
    @access_requests_ns.marshal_with(access_request_single_response_model, code=201)
    @requires_permission("access_requests", "create")
    def post(self):
        """Submit a new access request."""
        data = request.json or {}
        validate_access_request_create(data)
        
        service = get_service()
        try:
            req = service.submit_request(
                requester_id=UUID(g.user_id),
                business_justification=data["business_justification"],
                requested_role_id=UUID(data["requested_role_id"]) if data.get("requested_role_id") else None,
                requested_resource_id=UUID(data["requested_resource_id"]) if data.get("requested_resource_id") else None,
                priority=data.get("priority", "low"),
                requested_start=data.get("requested_start"),
                requested_end=data.get("requested_end")
            )
            return {
                "success": True,
                "message": "Access request created successfully",
                "data": req
            }, 201
        except AccessRequestDuplicateError as e:
            raise Conflict(str(e))
        except AccessRequestValidationError as e:
            raise UnprocessableEntity(str(e))

@access_requests_ns.route("/<uuid:request_id>")
class AccessRequestDetail(Resource):
    @access_requests_ns.doc("get_access_request")
    @access_requests_ns.marshal_with(access_request_single_response_model)
    @login_required
    def get(self, request_id):
        """Get an access request by ID."""
        service = get_service()
        req = service._repo.get_by_id(request_id)
        if not req:
            raise NotFound("Access request not found")
            
        authz = AuthorizationService(db.session)
        is_admin_or_auditor = authz.has_permission(UUID(g.user_id), "access_requests", PermissionAction.READ)
        if not is_admin_or_auditor and req.requester_id != UUID(g.user_id):
            raise NotFound("Access request not found") # Hide existence
            
        return {
            "success": True,
            "message": "Access request retrieved successfully",
            "data": req
        }

@access_requests_ns.route("/<uuid:request_id>/approve")
class AccessRequestApprove(Resource):
    @access_requests_ns.doc("approve_access_request")
    @access_requests_ns.marshal_with(access_request_single_response_model)
    @requires_permission("access_requests", "approve")
    def post(self, request_id):
        """Approve an access request."""
        service = get_service()
        try:
            req = service.approve_request(request_id, UUID(g.user_id))
            return {
                "success": True,
                "message": "Access request approved successfully",
                "data": req
            }
        except AccessRequestNotFoundError:
            raise NotFound("Access request not found")
        except AccessRequestInvalidStateError as e:
            raise BadRequest(str(e))
        except AccessRequestValidationError as e:
            raise UnprocessableEntity(str(e))

@access_requests_ns.route("/<uuid:request_id>/reject")
class AccessRequestReject(Resource):
    @access_requests_ns.doc("reject_access_request")
    @access_requests_ns.expect(access_request_reject_model)
    @access_requests_ns.marshal_with(access_request_single_response_model)
    @requires_permission("access_requests", "reject")
    def post(self, request_id):
        """Reject an access request."""
        data = request.json or {}
        reason = data.get("rejected_reason")
        if not reason:
            raise UnprocessableEntity("Missing rejected_reason")
            
        service = get_service()
        try:
            req = service.reject_request(request_id, reason, UUID(g.user_id))
            return {
                "success": True,
                "message": "Access request rejected successfully",
                "data": req
            }
        except AccessRequestNotFoundError:
            raise NotFound("Access request not found")
        except AccessRequestInvalidStateError as e:
            raise BadRequest(str(e))
        except AccessRequestValidationError as e:
            raise UnprocessableEntity(str(e))

@access_requests_ns.route("/<uuid:request_id>/cancel")
class AccessRequestCancel(Resource):
    @access_requests_ns.doc("cancel_access_request")
    @access_requests_ns.marshal_with(access_request_single_response_model)
    @requires_permission("access_requests", "cancel")
    def post(self, request_id):
        """Cancel an access request."""
        service = get_service()
        req = service._repo.get_by_id(request_id)
        if not req:
            raise NotFound("Access request not found")
            
        authz = AuthorizationService(db.session)
        is_admin = authz.has_permission(UUID(g.user_id), "access_requests", PermissionAction.READ)
        if not is_admin and req.requester_id != UUID(g.user_id):
            raise NotFound("Access request not found")
            
        try:
            cancelled_req = service.cancel_request(request_id)
            return {
                "success": True,
                "message": "Access request cancelled successfully",
                "data": cancelled_req
            }
        except AccessRequestNotFoundError:
            raise NotFound("Access request not found")
        except AccessRequestInvalidStateError as e:
            raise BadRequest(str(e))
        except AccessRequestValidationError as e:
            raise UnprocessableEntity(str(e))

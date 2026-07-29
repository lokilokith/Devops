"""Permissions REST API Routes."""
from flask import request
from flask_restx import Resource
from werkzeug.exceptions import NotFound

from app.api.responses import success_response
from app.api.decorators import login_required, requires_permission
from werkzeug.exceptions import Conflict
from app.permissions.schemas import (
    permissions_ns, permission_create_model, permission_update_model, permission_patch_model,
    permission_response_model, permission_list_response_model
)
from app.permissions.validators import (
    validate_permission_create, validate_permission_update, validate_permission_patch,
    validate_uuid, validate_pagination
)
from app.permissions.repository import PermissionsRepository
from app.permissions.service import PermissionsService
from app.permissions.exceptions import DuplicatePermissionError
from app.extensions import db

def get_service():
    return PermissionsService(PermissionsRepository(db.session))

@permissions_ns.route("")
class PermissionCollection(Resource):
    @permissions_ns.doc(summary="List permissions", description="Retrieve a paginated list of permissions.")
    @permissions_ns.marshal_with(permission_list_response_model)
    @login_required
    @requires_permission("permissions", "read")
    def get(self):
        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", 100))
        service = get_service()
        permissions = service.list_permissions(skip=skip, limit=limit)
        return success_response(data=permissions)

    @permissions_ns.doc(summary="Create permission", description="Create a new permission.")
    @permissions_ns.expect(permission_create_model)
    @permissions_ns.marshal_with(permission_response_model, code=201)
    @login_required
    @requires_permission("permissions", "create")
    def post(self):
        data = request.json or {}
        validate_permission_create(data)
        service = get_service()
        try:
            permission = service.create_permission(data)
            return success_response(data=permission, message="Permission created successfully", status_code=201)
        except DuplicatePermissionError as e:
            raise Conflict(str(e))

@permissions_ns.route("/<string:permission_id>")
class PermissionResource(Resource):
    @permissions_ns.doc(summary="Get permission", description="Retrieve a permission by UUID.")
    @permissions_ns.marshal_with(permission_response_model)
    @login_required
    @requires_permission("permissions", "read")
    def get(self, permission_id):
        uid = validate_uuid(permission_id)
        service = get_service()
        permission = service.get_permission(uid)
        if not permission:
            raise NotFound("Permission not found")
        return success_response(data=permission)

    @permissions_ns.doc(summary="Update permission", description="Completely update a permission by UUID.")
    @permissions_ns.expect(permission_update_model)
    @permissions_ns.marshal_with(permission_response_model)
    @login_required
    @requires_permission("permissions", "update")
    def put(self, permission_id):
        uid = validate_uuid(permission_id)
        data = request.json or {}
        validate_permission_update(data)
        service = get_service()
        try:
            permission = service.update_permission(uid, data)
            if not permission:
                raise NotFound("Permission not found")
            return success_response(data=permission, message="Permission updated successfully")
        except DuplicatePermissionError as e:
            raise Conflict(str(e))

    @permissions_ns.doc(summary="Partial update permission", description="Partially update a permission by UUID.")
    @permissions_ns.expect(permission_patch_model)
    @permissions_ns.marshal_with(permission_response_model)
    @login_required
    @requires_permission("permissions", "update")
    def patch(self, permission_id):
        uid = validate_uuid(permission_id)
        data = request.json or {}
        validate_permission_patch(data)
        service = get_service()
        try:
            permission = service.patch_permission(uid, data)
            if not permission:
                raise NotFound("Permission not found")
            return success_response(data=permission, message="Permission updated successfully")
        except DuplicatePermissionError as e:
            raise Conflict(str(e))

    @permissions_ns.doc(summary="Delete permission", description="Delete a permission by UUID.")
    @permissions_ns.marshal_with(permission_response_model)
    @login_required
    @requires_permission("permissions", "delete")
    def delete(self, permission_id):
        uid = validate_uuid(permission_id)
        service = get_service()
        permission = service.get_permission(uid)
        if not permission:
            raise NotFound("Permission not found")
        service.delete_permission(uid)
        return success_response(message="Permission deleted successfully")

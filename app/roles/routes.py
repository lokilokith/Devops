"""Roles REST API Routes."""
from flask import request
from app.api.pagination import validate_pagination, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from flask_restx import Resource
from werkzeug.exceptions import NotFound

from app.api.responses import success_response
from app.api.decorators import login_required, requires_permission
from werkzeug.exceptions import Conflict
from app.roles.schemas import (
    roles_ns, role_create_model, role_update_model, role_patch_model,
    role_response_model, role_list_response_model
)
from app.roles.validators import (
    validate_role_create, validate_role_update, validate_role_patch,
    validate_uuid
)
from app.roles.repository import RolesRepository
from app.roles.service import RolesService
from app.roles.exceptions import DuplicateRoleError
from app.extensions import db

def get_service():
    return RolesService(RolesRepository(db.session))

@roles_ns.route("")
class RoleCollection(Resource):
    @roles_ns.doc(summary="List roles", description="Retrieve a paginated list of roles.")
    @roles_ns.marshal_with(role_list_response_model)
    @login_required
    @requires_permission("roles", "read")
    def get(self):
        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        service = get_service()
        roles = service.list_roles(skip=skip, limit=limit)
        return success_response(data=roles)

    @roles_ns.doc(summary="Create role", description="Create a new role.")
    @roles_ns.expect(role_create_model)
    @roles_ns.marshal_with(role_response_model, code=201)
    @login_required
    @requires_permission("roles", "create")
    def post(self):
        data = request.json or {}
        validate_role_create(data)
        service = get_service()
        try:
            role = service.create_role(data)
            return success_response(data=role, message="Role created successfully", status_code=201)
        except DuplicateRoleError as e:
            raise Conflict(str(e))

@roles_ns.route("/<string:role_id>")
class RoleResource(Resource):
    @roles_ns.doc(summary="Get role", description="Retrieve a role by UUID.")
    @roles_ns.marshal_with(role_response_model)
    @login_required
    @requires_permission("roles", "read")
    def get(self, role_id):
        uid = validate_uuid(role_id)
        service = get_service()
        role = service.get_role(uid)
        if not role:
            raise NotFound("Role not found")
        return success_response(data=role)

    @roles_ns.doc(summary="Update role", description="Completely update a role by UUID.")
    @roles_ns.expect(role_update_model)
    @roles_ns.marshal_with(role_response_model)
    @login_required
    @requires_permission("roles", "update")
    def put(self, role_id):
        uid = validate_uuid(role_id)
        data = request.json or {}
        validate_role_update(data)
        service = get_service()
        try:
            role = service.update_role(uid, data)
            if not role:
                raise NotFound("Role not found")
            return success_response(data=role, message="Role updated successfully")
        except DuplicateRoleError as e:
            raise Conflict(str(e))

    @roles_ns.doc(summary="Partial update role", description="Partially update a role by UUID.")
    @roles_ns.expect(role_patch_model)
    @roles_ns.marshal_with(role_response_model)
    @login_required
    @requires_permission("roles", "update")
    def patch(self, role_id):
        uid = validate_uuid(role_id)
        data = request.json or {}
        validate_role_patch(data)
        service = get_service()
        try:
            role = service.patch_role(uid, data)
            if not role:
                raise NotFound("Role not found")
            return success_response(data=role, message="Role updated successfully")
        except DuplicateRoleError as e:
            raise Conflict(str(e))

    @roles_ns.doc(summary="Delete role", description="Delete a role by UUID.")
    @roles_ns.marshal_with(role_response_model)
    @login_required
    @requires_permission("roles", "delete")
    def delete(self, role_id):
        uid = validate_uuid(role_id)
        service = get_service()
        role = service.get_role(uid)
        if not role:
            raise NotFound("Role not found")
        service.delete_role(uid)
        return success_response(message="Role deleted successfully")

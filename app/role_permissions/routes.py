"""RolePermissions REST API Routes."""

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import NotFound

from app.api.responses import success_response
from app.api.decorators import login_required, requires_permission

from app.role_permissions.schemas import (
    role_permissions_ns,
    role_permission_response_model,
    role_permissions_list_response_model,
    permission_roles_list_response_model,
    role_permission_request_model,
)

from app.role_permissions.validators import (
    validate_uuid,
    validate_permission_assignment,
)

from app.role_permissions.service import RolePermissionService
from app.role_permissions.repository import RolePermissionsRepository
from app.roles.repository import RolesRepository
from app.permissions.repository import PermissionsRepository
from app.extensions import db
from app.role_permissions.exceptions import ValidationError

def get_service():
    return RolePermissionService(
        repository=RolePermissionsRepository(db.session),
        roles_repository=RolesRepository(db.session),
        permissions_repository=PermissionsRepository(db.session)
    )

@role_permissions_ns.route("roles/<string:role_id>/permissions")
class RolePermissionsCollection(Resource):
    @role_permissions_ns.doc(summary="List permissions for role", description="Retrieve all permissions assigned to a role.")
    @role_permissions_ns.marshal_with(role_permissions_list_response_model)
    @login_required
    @requires_permission("role_permissions", "manage")
    def get(self, role_id):
        uid = validate_uuid(role_id)
        service = get_service()
        try:
            permissions = service.list_permissions_for_role(uid)
            return success_response(data=permissions)
        except Exception:
            raise NotFound("Role not found")

    @role_permissions_ns.doc(summary="Assign permission to role", description="Assign a permission to a role.")
    @role_permissions_ns.expect(role_permission_request_model)
    @role_permissions_ns.marshal_with(role_permission_response_model, code=201)
    @login_required
    @requires_permission("role_permissions", "manage")
    def post(self, role_id):
        r_id = validate_uuid(role_id)
        data = request.json or {}
        p_id = validate_permission_assignment(data)
        
        user_id = None
        service = get_service()
        try:
            rp = service.assign_permission(r_id, p_id, user_id)
            return success_response(data={"role_id": str(rp.role_id), "permission_id": str(rp.permission_id)}, message="Permission assigned successfully", status_code=201)
        except ValidationError as e:
            if "already in use" in str(e) or "already assigned" in str(e).lower():
                from werkzeug.exceptions import Conflict
                raise Conflict(str(e))
            raise NotFound(str(e))

@role_permissions_ns.route("roles/<string:role_id>/permissions/<string:permission_id>")
class RolePermissionResource(Resource):
    @role_permissions_ns.doc(summary="Remove permission from role", description="Remove a permission from a role.")
    @role_permissions_ns.marshal_with(role_permission_response_model)
    @login_required
    @requires_permission("role_permissions", "manage")
    def delete(self, role_id, permission_id):
        r_id = validate_uuid(role_id)
        p_id = validate_uuid(permission_id)
        service = get_service()
        try:
            service.remove_permission(r_id, p_id)
            return success_response(message="Permission removed successfully")
        except ValidationError as e:
            raise NotFound(str(e))

@role_permissions_ns.route("permissions/<string:permission_id>/roles")
class PermissionRolesCollection(Resource):
    @role_permissions_ns.doc(summary="List roles for permission", description="Retrieve all roles that have a permission.")
    @role_permissions_ns.marshal_with(permission_roles_list_response_model)
    @login_required
    @requires_permission("role_permissions", "manage")
    def get(self, permission_id):
        uid = validate_uuid(permission_id)
        service = get_service()
        try:
            roles = service.list_roles_for_permission(uid)
            print("Route received:", roles, flush=True)
            print("Type of roles:", type(roles), flush=True)
            print("Item types:", [type(r) for r in roles], flush=True)
            return success_response(data=roles)
        except Exception:
            raise NotFound("Permission not found")

"""UserRoles REST API Routes."""

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import NotFound

from app.api.decorators import login_required, requires_permission
from app.api.responses import success_response
from app.extensions import db
from app.identity.repository import IdentityRepository
from app.roles.repository import RolesRepository
from app.user_roles.exceptions import ValidationError
from app.user_roles.repository import UserRolesRepository
from app.user_roles.schemas import (
    role_users_list_response_model,
    user_role_response_model,
    user_roles_list_response_model,
    user_roles_ns,
)
from app.user_roles.service import UserRoleService
from app.user_roles.validators import validate_role_assignment, validate_uuid


def get_service():
    return UserRoleService(
        repository=UserRolesRepository(db.session),
        roles_repository=RolesRepository(db.session),
        users_repository=IdentityRepository(db.session),
    )


@user_roles_ns.route("users/<string:user_id>/roles")
class UserRolesCollection(Resource):
    @user_roles_ns.doc(
        summary="List roles for user",
        description="Retrieve all roles assigned to a user.",
    )
    @user_roles_ns.marshal_with(user_roles_list_response_model)
    @login_required
    @requires_permission("user_roles", "manage")
    def get(self, user_id):
        uid = validate_uuid(user_id)
        service = get_service()
        try:
            roles = service.list_roles_for_user(uid)
            return success_response(data=roles)
        except Exception:
            raise NotFound("User not found")

    @user_roles_ns.doc(
        summary="Assign role to user", description="Assign a role to a user."
    )
    @user_roles_ns.marshal_with(user_role_response_model, code=201)
    @login_required
    @requires_permission("user_roles", "manage")
    def post(self, user_id):
        u_id = validate_uuid(user_id)
        data = request.json or {}
        r_id = validate_role_assignment(data)

        assigner_id = None
        service = get_service()
        try:
            ur = service.assign_role(u_id, r_id, assigner_id)
            return success_response(
                data={"user_id": str(ur.user_id), "role_id": str(ur.role_id)},
                message="Role assigned successfully",
                status_code=201,
            )
        except ValidationError as e:
            if "already in use" in str(e) or "already assigned" in str(e).lower():
                from werkzeug.exceptions import Conflict

                raise Conflict(str(e))
            raise NotFound(str(e))


@user_roles_ns.route("users/<string:user_id>/roles/<string:role_id>")
class UserRoleResource(Resource):
    @user_roles_ns.doc(
        summary="Remove role from user", description="Remove a role from a user."
    )
    @user_roles_ns.marshal_with(user_role_response_model)
    @login_required
    @requires_permission("user_roles", "manage")
    def delete(self, user_id, role_id):
        u_id = validate_uuid(user_id)
        r_id = validate_uuid(role_id)
        service = get_service()
        try:
            service.remove_role(u_id, r_id)
            return success_response(message="Role removed successfully")
        except ValidationError as e:
            raise NotFound(str(e))


@user_roles_ns.route("roles/<string:role_id>/users")
class RoleUsersCollection(Resource):
    @user_roles_ns.doc(
        summary="List users for role",
        description="Retrieve all users that have a role.",
    )
    @user_roles_ns.marshal_with(role_users_list_response_model)
    @login_required
    @requires_permission("user_roles", "manage")
    def get(self, role_id):
        uid = validate_uuid(role_id)
        service = get_service()
        try:
            users = service.list_users_for_role(uid)
            return success_response(data=users)
        except Exception:
            raise NotFound("Role not found")

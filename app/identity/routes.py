"""Identity REST API Routes."""
from uuid import UUID
from flask import request
from flask_restx import Resource
from werkzeug.exceptions import NotFound

from app.api.responses import success_response
from app.api.decorators import login_required, requires_permission
from werkzeug.exceptions import Conflict
from app.identity.schemas import (
    identity_ns, user_create_model, user_update_model, user_patch_model,
    user_response_model, user_list_response_model
)
from app.identity.validators import (
    validate_user_create, validate_user_update, validate_user_patch, validate_uuid
)
from app.identity.service import IdentityService
from app.identity.exceptions import DuplicateUserError
from app.extensions import db

from app.identity.repository import IdentityRepository
from app.auth.service import AuthService

def get_service():
    repo = IdentityRepository(db.session)
    return IdentityService(repo, AuthService(repo))

@identity_ns.route("")
class UserCollection(Resource):
    @identity_ns.doc(summary="List users", description="Retrieve a paginated list of users.")
    @identity_ns.marshal_with(user_list_response_model)
    @login_required
    @requires_permission("users", "read")
    def get(self):
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 100))
        service = get_service()
        users = service.list_users(skip=skip, limit=limit)
        return success_response(data=users)

    @identity_ns.doc(summary="Create user", description="Create a new user.")
    @identity_ns.expect(user_create_model)
    @identity_ns.marshal_with(user_response_model, code=201)
    @login_required
    @requires_permission("users", "create")
    def post(self):
        data = request.json or {}
        validate_user_create(data)
        service = get_service()
        try:
            user = service.create_user(data)
            return success_response(data=user, message="User created successfully", status_code=201)
        except DuplicateUserError as e:
            raise Conflict(str(e))

@identity_ns.route("/<string:user_id>")
class UserResource(Resource):
    @identity_ns.doc(summary="Get user", description="Retrieve a user by UUID.")
    @identity_ns.marshal_with(user_response_model)
    @login_required
    @requires_permission("users", "read")
    def get(self, user_id):
        uid = validate_uuid(user_id)
        service = get_service()
        user = service.get_user(uid)
        if not user:
            raise NotFound("User not found")
        return success_response(data=user)

    @identity_ns.doc(summary="Update user", description="Completely update a user by UUID.")
    @identity_ns.expect(user_update_model)
    @identity_ns.marshal_with(user_response_model)
    @login_required
    @requires_permission("users", "update")
    def put(self, user_id):
        uid = validate_uuid(user_id)
        data = request.json or {}
        validate_user_update(data)
        service = get_service()
        try:
            user = service.update_user(uid, data)
            if not user:
                raise NotFound("User not found")
            return success_response(data=user, message="User updated successfully")
        except DuplicateUserError as e:
            raise Conflict(str(e))

    @identity_ns.doc(summary="Partial update user", description="Partially update a user by UUID.")
    @identity_ns.expect(user_patch_model)
    @identity_ns.marshal_with(user_response_model)
    @login_required
    @requires_permission("users", "update")
    def patch(self, user_id):
        uid = validate_uuid(user_id)
        data = request.json or {}
        validate_user_patch(data)
        service = get_service()
        try:
            user = service.patch_user(uid, data)
            if not user:
                raise NotFound("User not found")
            return success_response(data=user, message="User updated successfully")
        except DuplicateUserError as e:
            raise Conflict(str(e))

    @identity_ns.doc(summary="Delete user", description="Delete a user by UUID.")
    @identity_ns.marshal_with(user_response_model)
    @login_required
    @requires_permission("users", "delete")
    def delete(self, user_id):
        uid = validate_uuid(user_id)
        service = get_service()
        user = service.get_user(uid)
        if not user:
            raise NotFound("User not found")
        service.delete_user(uid)
        return success_response(message="User deleted successfully")

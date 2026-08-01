"""Auth REST API Routes."""

import logging
from uuid import UUID
from flask import request, g
from flask_restx import Resource
from werkzeug.exceptions import Unauthorized, Forbidden

from app.api.responses import success_response
from app.api.decorators import login_required
from app.auth.schemas import (
    auth_ns,
    login_model,
    refresh_model,
    token_response_model,
    user_me_response_model,
)
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.auth.exceptions import InvalidCredentialsError, UserInactiveError
from app.extensions import db
from app.platform.extensions import limiter

logger = logging.getLogger(__name__)


def get_auth_service():
    return AuthService(IdentityRepository(db.session))


@auth_ns.route("/login")
class LoginResource(Resource):
    decorators = [limiter.limit("5 per minute")]

    @auth_ns.doc(summary="Login", description="Authenticate a user and return tokens.")
    @auth_ns.expect(login_model)
    @auth_ns.marshal_with(token_response_model)
    def post(self):
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            raise Unauthorized("Missing username or password")

        service = get_auth_service()
        try:
            tokens = service.authenticate_user(username, password)
            return success_response(
                data={
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens["refresh_token"],
                    "token_type": "Bearer",
                    "expires_in": tokens["expires_in"],
                },
                message="Login successful",
            )
        except InvalidCredentialsError:
            raise Unauthorized("Invalid credentials")
        except UserInactiveError:
            raise Forbidden("Inactive user")
        except Exception as exc:
            logger.exception("Unexpected error during login for user '%s'", username)
            raise


@auth_ns.route("/logout")
class LogoutResource(Resource):
    @auth_ns.doc(
        summary="Logout", description="Invalidate the current token.", security="Bearer"
    )
    @login_required
    def post(self):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            service = get_auth_service()
            service.revoke_token(token)

        return success_response(message="Logged out")


@auth_ns.route("/refresh")
class RefreshResource(Resource):
    decorators = [limiter.limit("5 per minute")]

    @auth_ns.doc(
        summary="Refresh Token", description="Refresh an existing access token."
    )
    @auth_ns.expect(refresh_model)
    @auth_ns.marshal_with(token_response_model)
    def post(self):
        data = request.json or {}
        refresh_token = data.get("refresh_token")

        if not refresh_token:
            raise Unauthorized("Missing refresh token")

        service = get_auth_service()
        try:
            tokens = service.refresh(refresh_token)
            return success_response(
                data={
                    "access_token": tokens["access_token"],
                    "token_type": "Bearer",
                    "expires_in": tokens["expires_in"],
                },
                message="Token refreshed successfully",
            )
        except (InvalidCredentialsError, UserInactiveError):
            raise Unauthorized("Invalid or inactive user")
        except Exception:
            raise Unauthorized("Invalid refresh token")


@auth_ns.route("/me")
class MeResource(Resource):
    @auth_ns.doc(
        summary="Get current user",
        description="Retrieve the authenticated user's profile.",
        security="Bearer",
    )
    @auth_ns.marshal_with(user_me_response_model)
    @login_required
    def get(self):
        user_id = UUID(g.user_id)
        repo = IdentityRepository(db.session)
        user = repo.get_by_id(user_id)
        if not user:
            raise Unauthorized("User not found")

        from sqlalchemy import select
        from app.roles.models import Role, UserRole
        from app.authorization.service import AuthorizationService

        roles = list(
            db.session.scalars(
                select(Role.role_name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            ).all()
        )

        authz_svc = AuthorizationService(db.session)
        raw_perms = authz_svc.get_user_permissions(user_id)

        # Map PERM_RESOURCE_ACTION to resource.action format
        permissions = []
        for p in raw_perms:
            if p.permission_code.startswith("PERM_"):
                # e.g., PERM_USERS_READ -> users.read
                parts = p.permission_code[5:].lower().rsplit("_", 1)
                if len(parts) == 2:
                    permissions.append(f"{parts[0]}.{parts[1]}")
                else:
                    permissions.append(p.permission_code.lower())

        return success_response(
            data={
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "roles": roles,
                "permissions": permissions,
            }
        )

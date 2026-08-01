"""API Decorators."""

from functools import wraps

from flask import g, request
from werkzeug.exceptions import Forbidden, Unauthorized

from app.auth.exceptions import TokenError, TokenExpiredError, TokenRevokedError
from app.auth.service import AuthService
from app.authorization.service import AuthorizationService
from app.extensions import db
from app.identity.repository import IdentityRepository
from app.permissions.models import PermissionAction


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Unauthorized("Missing or invalid authorization header")

        token = auth_header.split(" ")[1]

        try:
            auth_service = AuthService(IdentityRepository(db.session))
            payload = auth_service.verify_token(token, "access")
            g.user_id = payload["sub"]
        except TokenExpiredError:
            raise Unauthorized("Token has expired")
        except TokenRevokedError:
            raise Unauthorized("Token has been revoked")
        except TokenError:
            raise Unauthorized("Invalid token")

        return f(*args, **kwargs)

    return decorated_function


def requires_permission(resource_code: str, action: str):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            authz_service = AuthorizationService(db.session)

            try:
                perm_action = PermissionAction(action)
            except ValueError:
                raise Forbidden("Invalid permission action")

            from uuid import UUID

            has_perm = authz_service.has_permission(
                user_id=UUID(g.user_id), resource_code=resource_code, action=perm_action
            )

            if not has_perm:
                raise Forbidden("Insufficient permissions")

            return f(*args, **kwargs)

        return decorated_function

    return decorator


__all__ = ["login_required", "requires_permission"]

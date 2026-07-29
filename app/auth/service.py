"""Authentication Service."""
from __future__ import annotations
import datetime
from uuid import UUID

import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app

from app.identity.repository import IdentityRepository
from app.auth.exceptions import (
    InvalidCredentialsError,
    UserInactiveError,
    TokenError,
    TokenExpiredError,
    TokenRevokedError
)

_revoked_tokens = set()

class AuthService:
    def __init__(self, user_repo: IdentityRepository) -> None:
        self._user_repo = user_repo

    def hash_password(self, password: str) -> str:
        return generate_password_hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return check_password_hash(password_hash, password)

    def authenticate_user(self, username: str, password_raw: str) -> dict:
        user = self._user_repo.get_by_username(username)
        if not user:
            raise InvalidCredentialsError("Invalid username or password")
            
        if str(user.status.value) != "active":
            raise UserInactiveError("User is not active")
            
        if not user.password_hash or not self.verify_password(password_raw, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password")

        access_token = self.generate_access_token(user.id)
        refresh_token = self.generate_refresh_token(user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600
        }

    def _get_secret(self) -> str:
        return current_app.config.get("JWT_SECRET_KEY", "super-secret-default-key-at-least-32-bytes")

    def generate_access_token(self, user_id: UUID) -> str:
        payload = {
            "sub": str(user_id),
            "type": "access",
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(datetime.timezone.utc)
        }
        return jwt.encode(payload, self._get_secret(), algorithm="HS256")

    def generate_refresh_token(self, user_id: UUID) -> str:
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
            "iat": datetime.datetime.now(datetime.timezone.utc)
        }
        return jwt.encode(payload, self._get_secret(), algorithm="HS256")

    def verify_token(self, token: str, expected_type: str = "access") -> dict:
        if token in _revoked_tokens:
            raise TokenRevokedError("Token has been revoked")
        try:
            payload = jwt.decode(token, self._get_secret(), algorithms=["HS256"])
            if payload.get("type") != expected_type:
                raise TokenError("Invalid token type")
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenError(f"Invalid token: {e}")

    def revoke_token(self, token: str) -> None:
        try:
            _revoked_tokens.add(token)
        except Exception:
            pass

    def refresh(self, refresh_token: str) -> dict:
        payload = self.verify_token(refresh_token, expected_type="refresh")
        user_id = UUID(payload["sub"])
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise InvalidCredentialsError("User not found")
        if str(user.status.value) != "active":
            raise UserInactiveError("User is not active")
            
        access_token = self.generate_access_token(user_id)
        return {
            "access_token": access_token,
            "expires_in": 3600
        }

__all__ = ["AuthService"]

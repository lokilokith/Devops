"""Authentication Service."""

from __future__ import annotations
import datetime
import logging
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
    TokenRevokedError,
)

logger = logging.getLogger(__name__)


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

        try:
            status_val = (
                user.status.value if hasattr(user.status, "value") else str(user.status)
            )
            if status_val != "active":
                raise UserInactiveError("User is not active")
        except UserInactiveError:
            raise
        except Exception as exc:
            logger.error("Error checking user status for '%s': %s", username, exc)
            raise InvalidCredentialsError("Invalid username or password") from exc

        if not user.password_hash or not self.verify_password(
            password_raw, user.password_hash
        ):
            raise InvalidCredentialsError("Invalid username or password")

        access_token = self.generate_access_token(user.id)
        refresh_token = self.generate_refresh_token(user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
        }

    def _get_secret(self) -> str:
        secret = current_app.config.get("JWT_SECRET_KEY")
        if not secret:
            raise ValueError("JWT_SECRET_KEY is not configured.")
        return secret

    def generate_access_token(self, user_id: UUID) -> str:
        import uuid as uuid_module

        payload = {
            "jti": str(uuid_module.uuid4()),
            "sub": str(user_id),
            "type": "access",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(datetime.timezone.utc),
        }
        return jwt.encode(payload, self._get_secret(), algorithm="HS256")

    def generate_refresh_token(self, user_id: UUID) -> str:
        import uuid as uuid_module

        payload = {
            "jti": str(uuid_module.uuid4()),
            "sub": str(user_id),
            "type": "refresh",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
            "iat": datetime.datetime.now(datetime.timezone.utc),
        }
        return jwt.encode(payload, self._get_secret(), algorithm="HS256")

    def verify_token(self, token: str, expected_type: str = "access") -> dict:
        try:
            payload = jwt.decode(token, self._get_secret(), algorithms=["HS256"])

            from app.auth.models import RevokedToken
            from app.platform.extensions import db

            jti = payload.get("jti")
            if jti:
                revoked = db.session.query(RevokedToken).filter_by(jti=jti).first()
                if revoked:
                    raise TokenRevokedError("Token has been revoked")

            if payload.get("type") != expected_type:
                raise TokenError("Invalid token type")
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenError(f"Invalid token: {e}")

    def revoke_token(self, token: str) -> None:
        try:
            payload = jwt.decode(
                token,
                self._get_secret(),
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                from app.auth.models import RevokedToken
                from app.platform.extensions import db
                from datetime import datetime, timezone

                existing = db.session.query(RevokedToken).filter_by(jti=jti).first()
                if not existing:
                    revoked = RevokedToken(
                        jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)
                    )
                    db.session.add(revoked)
                    db.session.commit()
        except Exception as exc:
            logger.error("Failed to revoke token: %s", exc)

    def purge_expired_revoked_tokens(self) -> int:
        from app.auth.models import RevokedToken
        from app.platform.extensions import db
        from datetime import datetime, timezone

        try:
            now = datetime.now(timezone.utc)
            deleted_count = (
                db.session.query(RevokedToken)
                .filter(RevokedToken.expires_at < now)
                .delete(synchronize_session=False)
            )
            db.session.commit()
            return deleted_count
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to purge expired tokens: %s", exc)
            raise

    def refresh(self, refresh_token: str) -> dict:
        payload = self.verify_token(refresh_token, expected_type="refresh")
        user_id = UUID(payload["sub"])
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise InvalidCredentialsError("User not found")
        if str(user.status.value) != "active":
            raise UserInactiveError("User is not active")

        access_token = self.generate_access_token(user_id)
        return {"access_token": access_token, "expires_in": 3600}


__all__ = ["AuthService"]

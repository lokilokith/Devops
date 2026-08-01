import jwt
import pytest
from flask import current_app

from app.auth.exceptions import (
    InvalidCredentialsError,
    TokenError,
    TokenExpiredError,
    TokenRevokedError,
    UserInactiveError,
)
from app.identity.models import UserStatus


def test_password_hashing(auth_service):
    pwd = "my_secret_password"
    hashed = auth_service.hash_password(pwd)
    assert hashed != pwd
    assert auth_service.verify_password(pwd, hashed) is True
    assert auth_service.verify_password("wrong", hashed) is False


def test_authenticate_success(auth_service, sample_user):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    assert "access_token" in res
    assert "refresh_token" in res
    assert res["expires_in"] == 3600


def test_authenticate_invalid_username(auth_service, sample_user):
    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate_user("wronguser", "password123")


def test_authenticate_invalid_password(auth_service, sample_user):
    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate_user(sample_user.username, "wrongpass")


def test_authenticate_inactive_user(auth_service, sample_user, db_session):
    sample_user.status = UserStatus.SUSPENDED
    db_session.commit()
    with pytest.raises(UserInactiveError):
        auth_service.authenticate_user(sample_user.username, "password123")


def test_jwt_generation_and_validation(auth_service, sample_user):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    access_token = res["access_token"]

    payload = auth_service.verify_token(access_token, expected_type="access")
    assert payload["sub"] == str(sample_user.id)
    assert payload["type"] == "access"


def test_jwt_invalid_type(auth_service, sample_user):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    refresh_token = res["refresh_token"]

    with pytest.raises(TokenError, match="Invalid token type"):
        auth_service.verify_token(refresh_token, expected_type="access")


def test_jwt_expired(auth_service, sample_user, monkeypatch):
    import datetime

    # Generate token that is already expired
    payload = {
        "sub": str(sample_user.id),
        "type": "access",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    secret = current_app.config.get(
        "JWT_SECRET_KEY",
        "this-is-a-very-long-test-secret-key-that-is-at-least-32-bytes",
    )
    expired_token = jwt.encode(payload, secret, algorithm="HS256")

    with pytest.raises(TokenExpiredError):
        auth_service.verify_token(expired_token)


def test_jwt_revoked(auth_service, sample_user):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    access_token = res["access_token"]

    auth_service.revoke_token(access_token)

    with pytest.raises(TokenRevokedError):
        auth_service.verify_token(access_token)

    # revoking again shouldn't crash
    auth_service.revoke_token(access_token)


def test_jwt_invalid_signature(auth_service):
    with pytest.raises(TokenError):
        auth_service.verify_token("invalid.token.here")


def test_refresh_success(auth_service, sample_user):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    refresh_token = res["refresh_token"]

    new_res = auth_service.refresh(refresh_token)
    assert "access_token" in new_res
    assert new_res["expires_in"] == 3600


def test_refresh_inactive_user(auth_service, sample_user, db_session):
    res = auth_service.authenticate_user(sample_user.username, "password123")
    refresh_token = res["refresh_token"]

    sample_user.status = UserStatus.SUSPENDED
    db_session.commit()

    with pytest.raises(UserInactiveError):
        auth_service.refresh(refresh_token)


def test_revoke_token_exception(auth_service, monkeypatch):
    import app.auth.service

    monkeypatch.setattr(app.auth.service, "_revoked_tokens", None)
    # This will raise AttributeError inside revoke_token, which should be
    # caught and passed
    auth_service.revoke_token("some_token")

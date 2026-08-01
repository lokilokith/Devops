import datetime
from uuid import uuid4

import jwt
import pytest
from flask import current_app


def test_login_success(client, sample_user):
    # sample_user password is "Testpass123!" by default in factories or fixtures?
    # Actually, in most previous tests, password is set. Let's force it.
    from werkzeug.security import generate_password_hash

    from app.extensions import db

    sample_user.password_hash = generate_password_hash("password")
    db.session.commit()

    res = client.post(
        "/auth/login", json={"username": sample_user.username, "password": "password"}
    )
    assert res.status_code == 200
    assert "access_token" in res.json["data"]
    assert "refresh_token" in res.json["data"]


def test_login_wrong_password(client, sample_user):
    from werkzeug.security import generate_password_hash

    from app.extensions import db

    sample_user.password_hash = generate_password_hash("password")
    db.session.commit()

    res = client.post(
        "/auth/login", json={"username": sample_user.username, "password": "wrong"}
    )
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post(
        "/auth/login", json={"username": "unknown", "password": "password"}
    )
    assert res.status_code == 401


def test_login_inactive_user(client, sample_user):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.identity.models import UserStatus

    sample_user.password_hash = generate_password_hash("password")
    sample_user.status = UserStatus.DISABLED
    db.session.commit()

    res = client.post(
        "/auth/login", json={"username": sample_user.username, "password": "password"}
    )
    assert res.status_code == 403


def test_logout(client, auth_service, sample_user):
    token = auth_service.generate_access_token(sample_user.id)
    res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_refresh_success(client, auth_service, sample_user):
    token = auth_service.generate_refresh_token(sample_user.id)
    res = client.post("/auth/refresh", json={"refresh_token": token})
    assert res.status_code == 200
    assert "access_token" in res.json["data"]


def test_refresh_invalid(client):
    res = client.post("/auth/refresh", json={"refresh_token": "invalid"})
    assert res.status_code == 401


def test_me_success(client, auth_service, sample_user):
    token = auth_service.generate_access_token(sample_user.id)
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json["data"]["username"] == sample_user.username


def test_me_missing_token(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_expired_token(client, sample_user):
    payload = {
        "sub": str(sample_user.id),
        "type": "access",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=2),
    }
    token = jwt.encode(
        payload, current_app.config.get("JWT_SECRET_KEY"), algorithm="HS256"
    )
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_me_invalid_token(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})
    assert res.status_code == 401

import pytest
import json
from uuid import uuid4
from flask import Flask
from flask_restx import Api
from unittest.mock import MagicMock
from app.extensions import db
from app.api.errors import errors_bp
from app.identity.routes import identity_ns


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["JWT_SECRET_KEY"] = (
        "this-is-a-very-long-test-secret-key-that-is-at-least-32-bytes"
    )

    flask_app.register_blueprint(errors_bp)

    api = Api(flask_app)
    api.add_namespace(identity_ns, path="/users")

    db.init_app(flask_app)
    with flask_app.app_context():
        import app.identity.models
        import app.roles.models
        import app.resources.models
        import app.permissions.models
        import app.role_permissions.models

        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_auth(monkeypatch):
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: True,
    )


@pytest.fixture
def mock_service(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("app.identity.routes.get_service", lambda: mock)
    return mock


def test_list_users(client, mock_auth, mock_service):
    mock_service.list_users.return_value = [{"id": str(uuid4()), "username": "test"}]
    res = client.get(
        "/users?skip=0&limit=10", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_users_unauthorized(client):
    # No auth header
    res = client.get("/users")
    assert res.status_code == 401


def test_list_users_forbidden(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get("/users", headers={"Authorization": "Bearer token"})
    assert res.status_code == 403


def test_create_user(client, mock_auth, mock_service):
    mock_service.create_user.return_value = {"id": str(uuid4()), "username": "testuser"}
    data = {
        "employee_id": "E1",
        "username": "testuser",
        "email": "test@test.com",
        "full_name": "Test User",
        "password": "password123",
    }
    res = client.post("/users", json=data, headers={"Authorization": "Bearer token"})
    assert res.status_code == 201
    assert res.json["success"] is True


def test_create_user_validation_failure(client, mock_auth, mock_service):
    data = {"username": "testuser"}
    res = client.post("/users", json=data, headers={"Authorization": "Bearer token"})
    assert res.status_code == 422
    assert "Missing required field" in res.json["message"]


def test_get_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_user.return_value = {"id": uid, "username": "testuser"}
    res = client.get(f"/users/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200
    assert res.json["data"]["id"] == uid


def test_get_user_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_user.return_value = None
    res = client.get(f"/users/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_update_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_user.return_value = {"id": uid, "full_name": "Updated"}
    res = client.put(
        f"/users/{uid}",
        json={"full_name": "Updated", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["full_name"] == "Updated"


def test_update_user_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_user.return_value = None
    res = client.put(
        f"/users/{uid}",
        json={"full_name": "Updated", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_patch_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_user.return_value = {"id": uid, "full_name": "Patched"}
    res = client.patch(
        f"/users/{uid}",
        json={"full_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["full_name"] == "Patched"


def test_patch_user_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_user.return_value = None
    res = client.patch(
        f"/users/{uid}",
        json={"full_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_delete_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_user.return_value = {"id": uid}
    res = client.delete(f"/users/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200


def test_delete_user_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_user.return_value = None
    res = client.delete(f"/users/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get("/users/invalid-uuid", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422
    assert "Invalid UUID" in res.json["message"]


def test_validation_errors(client, mock_auth, mock_service):
    # Test all validation branches
    # Bad Email
    res = client.post(
        "/users",
        json={
            "employee_id": "E1",
            "username": "testuser",
            "email": "bad",
            "full_name": "Test User",
            "password": "password123",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Username too short
    res = client.post(
        "/users",
        json={
            "employee_id": "E1",
            "username": "ab",
            "email": "test@test.com",
            "full_name": "Test User",
            "password": "password123",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Username invalid chars
    res = client.post(
        "/users",
        json={
            "employee_id": "E1",
            "username": "ab!",
            "email": "test@test.com",
            "full_name": "Test User",
            "password": "password123",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Password too short
    res = client.post(
        "/users",
        json={
            "employee_id": "E1",
            "username": "testuser",
            "email": "test@test.com",
            "full_name": "Test User",
            "password": "short",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing employee id value
    res = client.post(
        "/users",
        json={
            "employee_id": "",
            "username": "testuser",
            "email": "test@test.com",
            "full_name": "Test User",
            "password": "password123",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Invalid manager id
    res = client.post(
        "/users",
        json={
            "employee_id": "E1",
            "username": "testuser",
            "email": "test@test.com",
            "full_name": "Test User",
            "password": "password123",
            "manager_user_id": "bad-uuid",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Invalid update missing full_name
    uid = str(uuid4())
    res = client.put(
        f"/users/{uid}",
        json={"full_name": "", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Invalid update missing status
    res = client.put(
        f"/users/{uid}",
        json={"full_name": "Updated", "status": ""},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422


def test_get_service(app):
    # Just to get 100% coverage on the get_service function
    from app.identity.routes import get_service

    # Re-mock it or run it in context
    with app.app_context():
        svc = get_service()
        assert svc is not None

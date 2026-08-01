from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import Flask
from flask_restx import Api

from app.api.errors import errors_bp
from app.extensions import db
from app.permissions.routes import permissions_ns


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
    api.add_namespace(permissions_ns, path="/permissions")

    db.init_app(flask_app)
    with flask_app.app_context():
        pass

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
    monkeypatch.setattr("app.permissions.routes.get_service", lambda: mock)
    return mock


def test_list_permissions(client, mock_auth, mock_service):
    mock_service.list_permissions.return_value = [
        {"id": str(uuid4()), "permission_name": "test"}
    ]
    res = client.get(
        "/permissions?skip=0&limit=10", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_permissions_unauthorized(client):
    res = client.get("/permissions")
    assert res.status_code == 401


def test_list_permissions_forbidden(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get("/permissions", headers={"Authorization": "Bearer token"})
    assert res.status_code == 403


def test_create_permission(client, mock_auth, mock_service):
    mock_service.create_permission.return_value = {
        "id": str(uuid4()),
        "permission_code": "PERM1",
    }
    data = {"permission_code": "PERM1", "permission_name": "Permission 1"}
    res = client.post(
        "/permissions", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 201
    assert res.json["success"] is True


def test_create_permission_validation_failure(client, mock_auth, mock_service):
    # Missing permission_name
    data = {"permission_code": "ADMIN"}
    res = client.post(
        "/permissions", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422

    # Permission code too short
    data = {"permission_code": "A", "permission_name": "Permission 1"}
    res = client.post(
        "/permissions", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422


def test_get_permission(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_permission.return_value = {"id": uid, "permission_name": "test"}
    res = client.get(f"/permissions/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200
    assert res.json["data"]["id"] == uid


def test_get_permission_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_permission.return_value = None
    res = client.get(f"/permissions/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_update_permission(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_permission.return_value = {
        "id": uid,
        "permission_name": "Updated",
    }
    res = client.put(
        f"/permissions/{uid}",
        json={"permission_name": "Updated", "action": "create", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["permission_name"] == "Updated"


def test_update_permission_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_permission.return_value = None
    res = client.put(
        f"/permissions/{uid}",
        json={"permission_name": "Updated", "action": "create", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_patch_permission(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_permission.return_value = {
        "id": uid,
        "permission_name": "Patched",
    }
    res = client.patch(
        f"/permissions/{uid}",
        json={"permission_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["permission_name"] == "Patched"


def test_patch_permission_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_permission.return_value = None
    res = client.patch(
        f"/permissions/{uid}",
        json={"permission_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_delete_permission(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_permission.return_value = {"id": uid}
    res = client.delete(
        f"/permissions/{uid}", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200


def test_delete_permission_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_permission.return_value = None
    res = client.delete(
        f"/permissions/{uid}", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get(
        "/permissions/invalid-uuid", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422
    assert "Invalid UUID" in res.json["message"]


def test_validation_errors(client, mock_auth, mock_service):
    # Permission code invalid chars
    res = client.post(
        "/permissions",
        json={"permission_code": "bad!", "permission_name": "Permission"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Permission name too short
    res = client.post(
        "/permissions",
        json={"permission_code": "GOOD", "permission_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing permission_name on update
    uid = str(uuid4())
    res = client.put(
        f"/permissions/{uid}",
        json={"status": "active", "action": "create"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing status on update
    res = client.put(
        f"/permissions/{uid}",
        json={"permission_name": "Name", "action": "create"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing action on update
    res = client.put(
        f"/permissions/{uid}",
        json={"permission_name": "Name", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Patch empty name
    res = client.patch(
        f"/permissions/{uid}",
        json={"permission_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Pagination invalid
    res = client.get("/permissions?skip=-1", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422

    res = client.get("/permissions?skip=abc", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422


def test_get_service(app):
    from app.permissions.routes import get_service

    with app.app_context():
        svc = get_service()
        assert svc is not None

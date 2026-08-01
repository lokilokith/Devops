from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import Flask
from flask_restx import Api

from app.api.errors import errors_bp
from app.extensions import db
from app.roles.routes import roles_ns


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
    api.add_namespace(roles_ns, path="/roles")

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
    monkeypatch.setattr("app.roles.routes.get_service", lambda: mock)
    return mock


def test_list_roles(client, mock_auth, mock_service):
    mock_service.list_roles.return_value = [{"id": str(uuid4()), "role_name": "test"}]
    res = client.get(
        "/roles?skip=0&limit=10", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_roles_unauthorized(client):
    res = client.get("/roles")
    assert res.status_code == 401


def test_list_roles_forbidden(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get("/roles", headers={"Authorization": "Bearer token"})
    assert res.status_code == 403


def test_create_role(client, mock_auth, mock_service):
    mock_service.create_role.return_value = {"id": str(uuid4()), "role_code": "ADMIN"}
    data = {"role_code": "ADMIN", "role_name": "Administrator"}
    res = client.post("/roles", json=data, headers={"Authorization": "Bearer token"})
    assert res.status_code == 201
    assert res.json["success"] is True


def test_create_role_validation_failure(client, mock_auth, mock_service):
    # Missing role_name
    data = {"role_code": "ADMIN"}
    res = client.post("/roles", json=data, headers={"Authorization": "Bearer token"})
    assert res.status_code == 422

    # Role code too short
    data = {"role_code": "A", "role_name": "Administrator"}
    res = client.post("/roles", json=data, headers={"Authorization": "Bearer token"})
    assert res.status_code == 422


def test_get_role(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_role.return_value = {"id": uid, "role_name": "test"}
    res = client.get(f"/roles/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200
    assert res.json["data"]["id"] == uid


def test_get_role_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_role.return_value = None
    res = client.get(f"/roles/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_update_role(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_role.return_value = {"id": uid, "role_name": "Updated"}
    res = client.put(
        f"/roles/{uid}",
        json={"role_name": "Updated", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["role_name"] == "Updated"


def test_update_role_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_role.return_value = None
    res = client.put(
        f"/roles/{uid}",
        json={"role_name": "Updated", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_patch_role(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_role.return_value = {"id": uid, "role_name": "Patched"}
    res = client.patch(
        f"/roles/{uid}",
        json={"role_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["role_name"] == "Patched"


def test_patch_role_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_role.return_value = None
    res = client.patch(
        f"/roles/{uid}",
        json={"role_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_delete_role(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_role.return_value = {"id": uid}
    res = client.delete(f"/roles/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200


def test_delete_role_not_found(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_role.return_value = None
    res = client.delete(f"/roles/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get("/roles/invalid-uuid", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422
    assert "Invalid UUID" in res.json["message"]


def test_validation_errors(client, mock_auth, mock_service):
    # Role code invalid chars
    res = client.post(
        "/roles",
        json={"role_code": "bad!", "role_name": "Role"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Role name too short
    res = client.post(
        "/roles",
        json={"role_code": "GOOD", "role_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing role_name on update
    uid = str(uuid4())
    res = client.put(
        f"/roles/{uid}",
        json={"status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing status on update
    res = client.put(
        f"/roles/{uid}",
        json={"role_name": "Name"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Patch empty name
    res = client.patch(
        f"/roles/{uid}",
        json={"role_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Pagination invalid
    res = client.get("/roles?skip=-1", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422

    res = client.get("/roles?skip=abc", headers={"Authorization": "Bearer token"})
    assert res.status_code == 422


def test_get_service(app):
    from app.roles.routes import get_service

    with app.app_context():
        svc = get_service()
        assert svc is not None

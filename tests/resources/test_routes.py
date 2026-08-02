from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import Flask

from app.api.errors import errors_bp
from app.extensions import db
from app.resources.routes import resources_ns
from app.routes.__init__ import CustomApi


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

    api = CustomApi(flask_app)
    api.add_namespace(resources_ns, path="/resources")

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
    monkeypatch.setattr("app.resources.routes.get_service", lambda: mock)
    return mock


def test_list_resources(client, mock_auth, mock_service):
    mock_service.list_resources.return_value = ([
        {"id": str(uuid4()), "resource_name": "test"}
    ], 1)
    res = client.get(
        "/resources?skip=0&limit=10", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_resources_unauthorized(client):
    res = client.get("/resources")
    assert res.status_code == 401


def test_list_resources_forbidden(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get("/resources", headers={"Authorization": "Bearer token"})
    assert res.status_code == 403


def test_create_resource(client, mock_auth, mock_service):
    mock_service.create_resource.return_value = {
        "id": str(uuid4()),
        "resource_code": "DB1",
    }
    data = {"resource_code": "DB1", "resource_name": "Database 1"}
    res = client.post(
        "/resources", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 201
    assert res.json["success"] is True


def test_create_resource_validation_failure(client, mock_auth, mock_service):
    # Missing resource_name
    data = {"resource_code": "ADMIN"}
    res = client.post(
        "/resources", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422

    # Resource code too short
    data = {"resource_code": "A", "resource_name": "Database 1"}
    res = client.post(
        "/resources", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422


def test_get_resource(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_resource.return_value = {"id": uid, "resource_name": "test"}
    res = client.get(f"/resources/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200
    assert res.json["data"]["id"] == uid


def test_get_resource_not_found(client, mock_auth, mock_service):
    from app.resources.exceptions import ResourceNotFoundError

    uid = str(uuid4())
    mock_service.get_resource.side_effect = ResourceNotFoundError(
        f"Resource {uid} not found"
    )
    res = client.get(f"/resources/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_update_resource(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.update_resource.return_value = {"id": uid, "resource_name": "Updated"}
    res = client.put(
        f"/resources/{uid}",
        json={
            "resource_name": "Updated",
            "resource_type": "database",
            "status": "active",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["resource_name"] == "Updated"


def test_update_resource_not_found(client, mock_auth, mock_service):
    from app.resources.exceptions import ResourceNotFoundError

    uid = str(uuid4())
    mock_service.update_resource.side_effect = ResourceNotFoundError(
        f"Resource {uid} not found"
    )
    res = client.put(
        f"/resources/{uid}",
        json={
            "resource_name": "Updated",
            "resource_type": "database",
            "status": "active",
        },
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_patch_resource(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.patch_resource.return_value = {"id": uid, "resource_name": "Patched"}
    res = client.patch(
        f"/resources/{uid}",
        json={"resource_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200
    assert res.json["data"]["resource_name"] == "Patched"


def test_patch_resource_not_found(client, mock_auth, mock_service):
    from app.resources.exceptions import ResourceNotFoundError

    uid = str(uuid4())
    mock_service.patch_resource.side_effect = ResourceNotFoundError(
        f"Resource {uid} not found"
    )
    res = client.patch(
        f"/resources/{uid}",
        json={"resource_name": "Patched"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_delete_resource(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.get_resource.return_value = {"id": uid}
    res = client.delete(f"/resources/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200


def test_delete_resource_not_found(client, mock_auth, mock_service):
    from app.resources.exceptions import ResourceNotFoundError

    uid = str(uuid4())
    mock_service.get_resource.side_effect = ResourceNotFoundError(
        f"Resource {uid} not found"
    )
    res = client.delete(f"/resources/{uid}", headers={"Authorization": "Bearer token"})
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get(
        "/resources/invalid-uuid", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422
    assert any("Invalid UUID" in str(err) for err in res.json["errors"])


def test_validation_errors(client, mock_auth, mock_service):
    # Resource code invalid chars
    res = client.post(
        "/resources",
        json={"resource_code": "bad!", "resource_name": "Resource"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Resource name too short
    res = client.post(
        "/resources",
        json={"resource_code": "GOOD", "resource_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing resource_name on update
    uid = str(uuid4())
    res = client.put(
        f"/resources/{uid}",
        json={"status": "active", "resource_type": "database"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing status on update
    res = client.put(
        f"/resources/{uid}",
        json={"resource_name": "Name", "resource_type": "database"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Missing resource_type on update
    res = client.put(
        f"/resources/{uid}",
        json={"resource_name": "Name", "status": "active"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Patch empty name
    res = client.patch(
        f"/resources/{uid}",
        json={"resource_name": "A"},
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Pagination invalid
    res = client.get("/resources?skip=-1", headers={"Authorization": "Bearer token"})
    assert res.status_code == 400

    res = client.get("/resources?skip=abc", headers={"Authorization": "Bearer token"})
    assert res.status_code == 400


def test_get_service(app):
    from app.resources.routes import get_service

    with app.app_context():
        svc = get_service()
        assert svc is not None

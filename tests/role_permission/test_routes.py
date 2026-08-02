from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import Flask
from flask_restx import Api

from app.api.errors import errors_bp
from app.extensions import db
from app.role_permissions.routes import role_permissions_ns


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
    api.add_namespace(role_permissions_ns, path="/")

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
    monkeypatch.setattr("app.role_permissions.routes.get_service", lambda: mock)
    return mock


def test_list_permissions_for_role(client, mock_auth, mock_service):
    role_id = str(uuid4())
    mock_service.list_permissions_for_role.return_value = (
        [{"id": str(uuid4()), "permission_name": "test"}],
        1,
    )
    res = client.get(
        f"/roles/{role_id}/permissions", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_permissions_for_role_unauthorized(client):
    role_id = str(uuid4())
    res = client.get(f"/roles/{role_id}/permissions")
    assert res.status_code == 401


def test_list_permissions_for_role_forbidden(client, monkeypatch):
    role_id = str(uuid4())
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get(
        f"/roles/{role_id}/permissions", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403


def test_list_permissions_for_role_not_found(client, mock_auth, mock_service):
    role_id = str(uuid4())
    mock_service.list_permissions_for_role.side_effect = Exception("fail")
    res = client.get(
        f"/roles/{role_id}/permissions", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_assign_permission(client, mock_auth, mock_service):
    role_id = str(uuid4())
    perm_id = str(uuid4())
    mock_rp = MagicMock()
    mock_rp.role_id = role_id
    mock_rp.permission_id = perm_id
    mock_service.assign_permission.return_value = mock_rp
    data = {"permission_id": perm_id}
    res = client.post(
        f"/roles/{role_id}/permissions",
        json=data,
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 201
    assert res.json["success"] is True


def test_assign_permission_conflict(client, mock_auth, mock_service):
    from app.role_permissions.exceptions import ValidationError

    role_id = str(uuid4())
    perm_id = str(uuid4())
    mock_service.assign_permission.side_effect = ValidationError(
        "Permission is already assigned"
    )
    data = {"permission_id": perm_id}
    res = client.post(
        f"/roles/{role_id}/permissions",
        json=data,
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 409


def test_assign_permission_not_found(client, mock_auth, mock_service):
    from app.role_permissions.exceptions import ValidationError

    role_id = str(uuid4())
    perm_id = str(uuid4())
    mock_service.assign_permission.side_effect = ValidationError("Role not found")
    data = {"permission_id": perm_id}
    res = client.post(
        f"/roles/{role_id}/permissions",
        json=data,
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_assign_permission_validation_failure(client, mock_auth, mock_service):
    role_id = str(uuid4())
    # Missing permission_id
    data = {}
    res = client.post(
        f"/roles/{role_id}/permissions",
        json=data,
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422

    # Invalid permission_id format
    data = {"permission_id": "invalid"}
    res = client.post(
        f"/roles/{role_id}/permissions",
        json=data,
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 422


def test_remove_permission(client, mock_auth, mock_service):
    role_id = str(uuid4())
    perm_id = str(uuid4())
    mock_service.remove_permission.return_value = True
    res = client.delete(
        f"/roles/{role_id}/permissions/{perm_id}",
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 200


def test_remove_permission_not_found(client, mock_auth, mock_service):
    from app.role_permissions.exceptions import ValidationError

    role_id = str(uuid4())
    perm_id = str(uuid4())
    mock_service.remove_permission.side_effect = ValidationError("Not found")
    res = client.delete(
        f"/roles/{role_id}/permissions/{perm_id}",
        headers={"Authorization": "Bearer token"},
    )
    assert res.status_code == 404


def test_list_roles_for_permission(client, mock_auth, mock_service):
    perm_id = str(uuid4())
    mock_service.list_roles_for_permission.return_value = (
        [{"id": str(uuid4()), "role_name": "test"}],
        1,
    )
    res = client.get(
        f"/permissions/{perm_id}/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_roles_for_permission_not_found(client, mock_auth, mock_service):
    perm_id = str(uuid4())
    mock_service.list_roles_for_permission.side_effect = Exception("fail")
    res = client.get(
        f"/permissions/{perm_id}/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get(
        "/roles/invalid-uuid/permissions", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422


def test_get_service(app):
    from app.role_permissions.routes import get_service

    with app.app_context():
        svc = get_service()
        assert svc is not None

import pytest
from uuid import uuid4
from flask import Flask
from flask_restx import Api
from unittest.mock import MagicMock
from app.extensions import db
from app.api.errors import errors_bp
from app.user_roles.routes import user_roles_ns


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
    api.add_namespace(user_roles_ns, path="/")

    db.init_app(flask_app)
    with flask_app.app_context():
        import app.identity.models
        import app.roles.models

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
    monkeypatch.setattr("app.user_roles.routes.get_service", lambda: mock)
    return mock


def test_list_roles_for_user(client, mock_auth, mock_service):
    user_id = str(uuid4())
    mock_service.list_roles_for_user.return_value = [
        {"id": str(uuid4()), "role_name": "test"}
    ]
    res = client.get(
        f"/users/{user_id}/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_roles_for_user_unauthorized(client):
    user_id = str(uuid4())
    res = client.get(f"/users/{user_id}/roles")
    assert res.status_code == 401


def test_list_roles_for_user_forbidden(client, monkeypatch):
    user_id = str(uuid4())
    monkeypatch.setattr(
        "app.auth.service.AuthService.verify_token",
        lambda *args, **kwargs: {"sub": str(uuid4())},
    )
    monkeypatch.setattr(
        "app.authorization.service.AuthorizationService.has_permission",
        lambda *args, **kwargs: False,
    )
    res = client.get(
        f"/users/{user_id}/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403


def test_list_roles_for_user_not_found(client, mock_auth, mock_service):
    user_id = str(uuid4())
    mock_service.list_roles_for_user.side_effect = Exception("fail")
    res = client.get(
        f"/users/{user_id}/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_assign_role(client, mock_auth, mock_service):
    user_id = str(uuid4())
    role_id = str(uuid4())
    mock_ur = MagicMock()
    mock_ur.user_id = user_id
    mock_ur.role_id = role_id
    mock_service.assign_role.return_value = mock_ur
    data = {"role_id": role_id}
    res = client.post(
        f"/users/{user_id}/roles", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 201
    assert res.json["success"] is True


def test_assign_role_conflict(client, mock_auth, mock_service):
    from app.user_roles.exceptions import ValidationError

    user_id = str(uuid4())
    role_id = str(uuid4())
    mock_service.assign_role.side_effect = ValidationError("Role is already assigned")
    data = {"role_id": role_id}
    res = client.post(
        f"/users/{user_id}/roles", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 409


def test_assign_role_not_found(client, mock_auth, mock_service):
    from app.user_roles.exceptions import ValidationError

    user_id = str(uuid4())
    role_id = str(uuid4())
    mock_service.assign_role.side_effect = ValidationError("User not found")
    data = {"role_id": role_id}
    res = client.post(
        f"/users/{user_id}/roles", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_assign_role_validation_failure(client, mock_auth, mock_service):
    user_id = str(uuid4())
    # Missing role_id
    data = {}
    res = client.post(
        f"/users/{user_id}/roles", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422

    # Invalid role_id format
    data = {"role_id": "invalid"}
    res = client.post(
        f"/users/{user_id}/roles", json=data, headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422


def test_remove_role(client, mock_auth, mock_service):
    user_id = str(uuid4())
    role_id = str(uuid4())
    mock_service.remove_role.return_value = True
    res = client.delete(
        f"/users/{user_id}/roles/{role_id}", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200


def test_remove_role_not_found(client, mock_auth, mock_service):
    from app.user_roles.exceptions import ValidationError

    user_id = str(uuid4())
    role_id = str(uuid4())
    mock_service.remove_role.side_effect = ValidationError("Not found")
    res = client.delete(
        f"/users/{user_id}/roles/{role_id}", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_list_users_for_role(client, mock_auth, mock_service):
    role_id = str(uuid4())
    mock_service.list_users_for_role.return_value = [
        {"id": str(uuid4()), "username": "test"}
    ]
    res = client.get(
        f"/roles/{role_id}/users", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["data"]) == 1


def test_list_users_for_role_not_found(client, mock_auth, mock_service):
    role_id = str(uuid4())
    mock_service.list_users_for_role.side_effect = Exception("fail")
    res = client.get(
        f"/roles/{role_id}/users", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 404


def test_invalid_uuid(client, mock_auth):
    res = client.get(
        "/users/invalid-uuid/roles", headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 422


def test_get_service(app):
    from app.user_roles.routes import get_service

    with app.app_context():
        svc = get_service()
        assert svc is not None

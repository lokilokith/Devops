import datetime

import jwt
import pytest
from flask import jsonify

from app.api.decorators import login_required, requires_permission
from app.auth.service import AuthService
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository
from app.permissions.models import Permission, PermissionAction
from app.resources.models import Resource
from app.role_permissions.models import RolePermission
from app.roles.models import Role, RoleStatus, RoleType, UserRole


def setup_app_routes(app):
    @app.route("/protected")
    @login_required
    def protected():
        return jsonify({"success": True})

    @app.route("/admin")
    @requires_permission("ADMIN_RES", "read")
    def admin():
        return jsonify({"success": True})


def create_mock_token(
    app, user_id, expired=False, revoked=False, invalid=False, token_type="access"
):
    if invalid:
        return "invalid.token.here"

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=-1 if expired else 1),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }

    token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")

    if revoked:
        from app.auth.service import _revoked_tokens

        _revoked_tokens.add(token)

    return token


def test_login_required_no_token(app, client):
    setup_app_routes(app)
    res = client.get("/protected")
    assert res.status_code == 401


def test_login_required_invalid_format(app, client):
    setup_app_routes(app)
    res = client.get("/protected", headers={"Authorization": "Token something"})
    assert res.status_code == 401


def test_login_required_success(app, client, db_session):
    setup_app_routes(app)
    from uuid import uuid4

    uid = uuid4()
    token = create_mock_token(app, uid)

    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_login_required_expired(app, client):
    setup_app_routes(app)
    from uuid import uuid4

    token = create_mock_token(app, uuid4(), expired=True)

    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "expired" in res.json["message"]


def test_login_required_revoked(app, client):
    setup_app_routes(app)
    from uuid import uuid4

    token = create_mock_token(app, uuid4(), revoked=True)

    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "revoked" in res.json["message"]


def test_login_required_invalid(app, client):
    setup_app_routes(app)
    from uuid import uuid4

    token = create_mock_token(app, uuid4(), invalid=True)

    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Invalid token" in res.json["message"]


def test_requires_permission_success(app, client, db_session):
    setup_app_routes(app)
    u = User(
        employee_id="P1",
        username="p1",
        email="p1@a.c",
        full_name="P1",
        status=UserStatus.ACTIVE,
    )
    r = Role(
        role_code="ADM",
        role_name="Admin",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    res_obj = Resource(resource_code="ADMIN_RES", resource_name="Admin Res")
    perm = Permission(
        permission_code="PERM_ADMIN_RES_READ",
        permission_name="Admin Res",
        action=PermissionAction.READ,
        description="read admin",
        status="active",
    )
    db_session.add_all([u, r, res_obj, perm])
    db_session.flush()

    rp = RolePermission(role_id=r.id, permission_id=perm.id)
    ur = UserRole(user_id=u.id, role_id=r.id)
    db_session.add_all([rp, ur])
    db_session.commit()

    token = create_mock_token(app, u.id)
    res = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_requires_permission_denied(app, client, db_session):
    setup_app_routes(app)
    u = User(
        employee_id="P2",
        username="p2",
        email="p2@a.c",
        full_name="P2",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()

    token = create_mock_token(app, u.id)
    res = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    print(res.json)
    assert res.status_code == 403


def test_requires_permission_invalid_action(app, client):
    @app.route("/invalid_action")
    @requires_permission("ADMIN_RES", "invalid_action_here")
    def inv():
        return jsonify({"success": True})

    from uuid import uuid4

    token = create_mock_token(app, uuid4())
    res = client.get("/invalid_action", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "Invalid permission action" in res.json["message"]

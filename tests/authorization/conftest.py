import pytest
from flask import Flask
from app.extensions import db
from app.authorization.service import AuthorizationService
from app.identity.models import User, UserStatus
from app.roles.models import Role, RoleType, RoleStatus, UserRole
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.role_permissions.models import RolePermission
from app.resources.models import Resource, ResourceType, ResourceStatus


@pytest.fixture
def auth_mock_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def auth_mock_db_session(auth_mock_app):
    yield db.session
    db.session.rollback()
    db.session.remove()


@pytest.fixture
def auth_test_service(auth_mock_db_session):
    return AuthorizationService(auth_mock_db_session)


@pytest.fixture
def populated_db(auth_mock_db_session):
    db_session = auth_mock_db_session
    u1 = User(
        employee_id="U1",
        username="u1",
        email="u1@e.com",
        full_name="u1",
        status=UserStatus.ACTIVE,
    )
    u2 = User(
        employee_id="U2",
        username="u2",
        email="u2@e.com",
        full_name="u2",
        status=UserStatus.ACTIVE,
    )
    u3 = User(
        employee_id="U3",
        username="u3",
        email="u3@e.com",
        full_name="u3",
        status=UserStatus.ACTIVE,
    )
    db_session.add_all([u1, u2, u3])

    r1 = Role(
        role_code="ROL1",
        role_name="R1",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    r2 = Role(
        role_code="ROL2",
        role_name="R2",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add_all([r1, r2])

    p1 = Permission(
        permission_code="PERM_RES1_READ",
        permission_name="P1",
        action=PermissionAction.READ,
        status=PermissionStatus.ACTIVE,
    )
    p2 = Permission(
        permission_code="PERM_RES2_DELETE",
        permission_name="P2",
        action=PermissionAction.DELETE,
        status=PermissionStatus.ACTIVE,
    )
    db_session.add_all([p1, p2])

    res1 = Resource(
        resource_code="RES1",
        resource_name="Res1",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
    )
    res2 = Resource(
        resource_code="RES2",
        resource_name="Res2",
        resource_type=ResourceType.DATABASE,
        status=ResourceStatus.ACTIVE,
    )
    db_session.add_all([res1, res2])

    db_session.commit()

    # Assign Roles
    db_session.add(UserRole(user_id=u1.id, role_id=r1.id))
    db_session.add(UserRole(user_id=u2.id, role_id=r2.id))
    # Duplicate mapping test support
    db_session.add(UserRole(user_id=u1.id, role_id=r2.id))

    # Assign Permissions
    db_session.add(RolePermission(role_id=r1.id, permission_id=p1.id))
    db_session.add(RolePermission(role_id=r2.id, permission_id=p2.id))
    db_session.commit()

    return {
        "users": {"u1": u1, "u2": u2, "u3": u3},
        "roles": {"r1": r1, "r2": r2},
        "permissions": {"p1": p1, "p2": p2},
        "resources": {"res1": res1, "res2": res2},
    }

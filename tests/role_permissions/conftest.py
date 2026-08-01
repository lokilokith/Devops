import pytest
from flask import Flask
from app.extensions import db
from app.role_permissions.repository import RolePermissionsRepository
from app.roles.models import Role, RoleType, RoleStatus
from app.permissions.models import Permission, PermissionAction, PermissionStatus


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        import app.identity.models
        import app.roles.models
        import app.permissions.models
        import app.role_permissions.models

        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def db_session(app):
    yield db.session
    db.session.rollback()
    db.session.remove()


@pytest.fixture
def role_permissions_repo(db_session):
    return RolePermissionsRepository(db_session)


@pytest.fixture
def sample_role(db_session):
    role = Role(
        role_code="RP_ROLE",
        role_name="Role for RP",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture
def sample_permission(db_session):
    perm = Permission(
        permission_code="RP_PERM",
        permission_name="Perm for RP",
        action=PermissionAction.READ,
        status=PermissionStatus.ACTIVE,
    )
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm

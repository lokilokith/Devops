import pytest
from flask import Flask
from app.extensions import db
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.permissions.repository import PermissionsRepository


@pytest.fixture
def app():
    """Build a Flask testing application with an in-memory SQLite database."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        import app.identity.models
        import app.roles.models
        import app.resources.models
        import app.permissions.models

        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def db_session(app):
    """Provide an isolated database session."""
    yield db.session
    db.session.rollback()
    db.session.remove()


@pytest.fixture
def permissions_repo(db_session):
    """Repository fixture for testing."""
    return PermissionsRepository(db_session)


@pytest.fixture
def sample_permission(db_session):
    """A sample active read permission."""
    permission = Permission(
        permission_code="SMPL_PERM",
        permission_name="Sample Permission",
        action=PermissionAction.READ,
        description="A sample permission for testing",
        status=PermissionStatus.ACTIVE,
    )
    db_session.add(permission)
    db_session.commit()
    db_session.refresh(permission)
    return permission

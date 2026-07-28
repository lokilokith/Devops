import pytest
from flask import Flask
from app.extensions import db
from app.roles.models import Role, RoleType, RoleStatus
from app.roles.repository import RolesRepository
import app.identity.models
import app.roles.models

@pytest.fixture
def app():
    """Build a Flask testing application with an in-memory SQLite database."""
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
def db_session(app):
    """Provide an isolated database session."""
    yield db.session
    db.session.rollback()
    db.session.remove()

@pytest.fixture
def roles_repo(db_session):
    """Repository fixture for testing."""
    return RolesRepository(db_session)

@pytest.fixture
def sample_role(db_session):
    """A sample active system role."""
    role = Role(
        role_code="SMPL",
        role_name="Sample Role",
        role_type=RoleType.SYSTEM,
        description="A sample role for testing",
        status=RoleStatus.ACTIVE
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role

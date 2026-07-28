import pytest
from flask import Flask
from app.extensions import db
from app.user_roles.repository import UserRolesRepository
from app.roles.models import Role, RoleType, RoleStatus
from app.identity.models import User, UserStatus

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
def user_roles_repo(db_session):
    return UserRolesRepository(db_session)

@pytest.fixture
def sample_user(db_session):
    user = User(
        employee_id="E123",
        username="testuser",
        email="testuser@example.com",
        full_name="Test User",
        status=UserStatus.ACTIVE
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def sample_role(db_session):
    role = Role(
        role_code="UR_ROLE",
        role_name="Role for UR",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role

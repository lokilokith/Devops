import pytest
from flask import Flask
from app.extensions import db
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.identity.models import User, UserStatus
import uuid

@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["JWT_SECRET_KEY"] = "this-is-a-very-long-test-secret-key-that-is-at-least-32-bytes"
    
    from app.auth.routes import auth_ns
    from flask_restx import Api
    
    api = Api(flask_app)
    api.add_namespace(auth_ns, path="/auth")
    
    db.init_app(flask_app)
    with flask_app.app_context():
        import app.identity.models
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db_session(app):
    yield db.session
    db.session.rollback()
    db.session.remove()

@pytest.fixture
def user_repo(db_session):
    return IdentityRepository(db_session)

@pytest.fixture
def auth_service(user_repo):
    return AuthService(user_repo)

@pytest.fixture
def sample_user(db_session, auth_service):
    u = User(
        employee_id="E123",
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        status=UserStatus.ACTIVE,
        password_hash=auth_service.hash_password("password123")
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u

import pytest
from flask import Flask
from app.extensions import db
from app.audit.repository import AuditRepository
from app.audit.service import AuditService

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        import app.audit.models
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
def audit_repo(db_session):
    return AuditRepository(db_session)

@pytest.fixture
def audit_service(audit_repo):
    return AuditService(audit_repo)

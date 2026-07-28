import pytest
from flask import Flask
from app.extensions import db
from app.resources.models import Resource, ResourceType, ResourceStatus
from app.resources.repository import ResourcesRepository

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
def resources_repo(db_session):
    """Repository fixture for testing."""
    return ResourcesRepository(db_session)

@pytest.fixture
def sample_resource(db_session):
    """A sample active server resource."""
    resource = Resource(
        resource_code="SMPL_RES",
        resource_name="Sample Resource",
        resource_type=ResourceType.SERVER,
        description="A sample resource for testing",
        status=ResourceStatus.ACTIVE
    )
    db_session.add(resource)
    db_session.commit()
    db_session.refresh(resource)
    return resource

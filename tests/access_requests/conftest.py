import pytest
from flask import Flask
from app.extensions import db
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.service import AccessRequestService
from app.identity.models import User, UserStatus
from app.roles.models import Role, RoleType, RoleStatus
from app.resources.models import Resource, ResourceType, ResourceStatus
from app.identity.repository import IdentityRepository
from app.roles.repository import RolesRepository
from app.resources.repository import ResourcesRepository


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
        import app.resources.models
        import app.access_requests.models

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
def ar_repo(db_session):
    return AccessRequestRepository(db_session)


@pytest.fixture
def ar_service(db_session, ar_repo):
    user_repo = IdentityRepository(db_session)
    role_repo = RolesRepository(db_session)
    resource_repo = ResourcesRepository(db_session)
    return AccessRequestService(ar_repo, user_repo, role_repo, resource_repo)


@pytest.fixture
def sample_user(db_session):
    u = User(
        employee_id="ARU1",
        username="aru1",
        email="aru1@e.com",
        full_name="AR U1",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def sample_role(db_session):
    r = Role(
        role_code="ARROL",
        role_name="AR Role",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def sample_resource(db_session):
    res = Resource(
        resource_code="ARRES",
        resource_name="AR Resource",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
    )
    db_session.add(res)
    db_session.commit()
    return res

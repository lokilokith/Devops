import pytest
from flask import Flask
from app.extensions import db
from app.approval_workflow.repository import ApprovalWorkflowRepository
from app.approval_workflow.service import ApprovalWorkflowService
from app.access_requests.repository import AccessRequestRepository
from app.user_roles.repository import UserRolesRepository
from app.identity.models import User, UserStatus
from app.roles.models import Role, RoleType, RoleStatus
from app.access_requests.models import AccessRequest, AccessRequestStatus, AccessRequestPriority

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
        import app.approval_workflow.models

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
def approval_repo(db_session):
    return ApprovalWorkflowRepository(db_session)

@pytest.fixture
def ar_repo(db_session):
    return AccessRequestRepository(db_session)

@pytest.fixture
def ur_repo(db_session):
    return UserRolesRepository(db_session)

@pytest.fixture
def audit_service():
    from app.audit.service import AuditService
    from unittest.mock import MagicMock
    return MagicMock(spec=AuditService)

@pytest.fixture
def approval_service(db_session, approval_repo, ar_repo, ur_repo, audit_service):
    return ApprovalWorkflowService(approval_repo, ar_repo, ur_repo, audit_service, db_session)

@pytest.fixture
def sample_users(db_session):
    u1 = User(employee_id="AWU1", username="awu1", email="awu1@e.com", full_name="AW U1", status=UserStatus.ACTIVE)
    u2 = User(employee_id="AWU2", username="awu2", email="awu2@e.com", full_name="AW U2", status=UserStatus.ACTIVE)
    db_session.add_all([u1, u2])
    db_session.commit()
    return u1, u2

@pytest.fixture
def sample_role(db_session):
    r = Role(role_code="AWROL", role_name="AW Role", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    db_session.add(r)
    db_session.commit()
    return r

@pytest.fixture
def sample_request(db_session, sample_users, sample_role):
    u1, _ = sample_users
    req = AccessRequest(
        request_number="AW-REQ-1",
        requester_id=u1.id,
        requested_role_id=sample_role.id,
        business_justification="Test",
        status=AccessRequestStatus.PENDING,
        priority=AccessRequestPriority.LOW
    )
    db_session.add(req)
    db_session.commit()
    return req

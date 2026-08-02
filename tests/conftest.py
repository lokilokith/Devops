import os

import pytest

from app import create_app
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.shared.database import db as _db
from tests.fixtures.factories import UserFactory


@pytest.fixture(scope="session")
def app():
    os.environ["APP_ENV"] = "testing"
    os.environ["SECRET_KEY"] = "super-secret-key-for-testing-12345678"
    app = create_app()
    with app.app_context():
        from app.identity.models import User
        from app.roles.models import Role, UserRole
        from app.permissions.models import Permission
        from app.role_permissions.models import RolePermission
        from app.resources.models import Resource
        from app.auth.models import RevokedToken
        from app.approval_workflow.models import ApprovalWorkflow
        from app.access_requests.models import AccessRequest
        from app.notifications.models import Notification
        from app.audit.models import AuditLog
        
        _db.create_all()
        # Ensure RBAC is seeded
        from app.security.bootstrap.rbac_seed_service import seed_rbac

        seed_rbac()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    session = _db.session
    session.begin_nested()

    from tests.fixtures import factories

    for f in [
        factories.UserFactory,
        factories.RoleFactory,
        factories.PermissionFactory,
        factories.WorkflowFactory,
        factories.NotificationFactory,
        factories.AccessRequestFactory,
    ]:
        f._meta.sqlalchemy_session = session

    yield session

    session.rollback()
    session.remove()


@pytest.fixture
def security_auth_service(db_session):
    return AuthService(IdentityRepository(db_session))


@pytest.fixture
def admin_user(db_session):
    from app.identity.models import User

    # the bootstrap created an 'admin' user
    user = db_session.query(User).filter_by(username="admin").first()
    if not user:
        user = UserFactory(username="admin")
        db_session.add(user)
        db_session.commit()
    return user


@pytest.fixture
def admin_token(security_auth_service, admin_user):
    return security_auth_service.generate_access_token(admin_user.id)


@pytest.fixture
def normal_user(db_session):
    user = UserFactory()
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def normal_token(security_auth_service, normal_user):
    return security_auth_service.generate_access_token(normal_user.id)


@pytest.fixture
def approver_user(db_session):
    user = UserFactory(username="approver")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def approver_token(security_auth_service, approver_user):
    return security_auth_service.generate_access_token(approver_user.id)


@pytest.fixture
def sec_admin_user(db_session):
    from app.roles.models import Role

    user = UserFactory(username="sec_admin")
    sec_admin_role = db_session.query(Role).filter_by(role_code="SEC_ADMIN").first()
    if sec_admin_role:
        from app.roles.models import UserRole

        db_session.add(UserRole(user_id=user.id, role_id=sec_admin_role.id))
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sec_admin_token(security_auth_service, sec_admin_user):
    return security_auth_service.generate_access_token(sec_admin_user.id)

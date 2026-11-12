import base64
import os

import pytest

from app import create_app
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.shared.database import db as _db
from tests.fixtures.factories import RoleFactory, UserFactory


@pytest.fixture(scope="session")
def app():
    os.environ["APP_ENV"] = "testing"
    os.environ["SECRET_KEY"] = "super-secret-key-for-testing-12345678"
    # Ensure master key is set for KMS provider initialization
    os.environ["VAULT_MASTER_KEY"] = base64.b64encode(os.urandom(32)).decode()

    app = create_app(testing_bootstrap=True)
    with app.app_context():
        yield app
        _db.session.remove()
        _db.engine.dispose()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    session = _db.session
    session.begin_nested()
    # Patch commit to flush to prevent test data from leaking
    original_commit = session.commit  # noqa: F841 – saved for potential restore
    session.commit = session.flush

    from tests.fixtures import factories

    for f in [
        factories.UserFactory,
        factories.RoleFactory,
        factories.PermissionFactory,
        factories.WorkflowFactory,
        factories.NotificationFactory,
        factories.AccessRequestFactory,
        factories.ResourceFactory,
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
        db_session.flush()
    return user


@pytest.fixture
def admin_token(security_auth_service, admin_user):
    return security_auth_service.generate_access_token(admin_user.id)


@pytest.fixture
def normal_user(db_session):
    user = UserFactory()
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def normal_token(security_auth_service, normal_user):
    return security_auth_service.generate_access_token(normal_user.id)


@pytest.fixture
def user_token(security_auth_service, normal_user):
    return security_auth_service.generate_access_token(normal_user.id)


@pytest.fixture
def approver_user(db_session):
    user = UserFactory(username="approver")
    db_session.add(user)
    db_session.flush()
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
    db_session.flush()
    return user


@pytest.fixture
def sec_admin_token(security_auth_service, sec_admin_user):
    return security_auth_service.generate_access_token(sec_admin_user.id)


@pytest.fixture
def test_role(db_session):
    role = RoleFactory()
    db_session.add(role)
    db_session.flush()
    return role


@pytest.fixture
def test_user(db_session):
    user = UserFactory()
    db_session.add(user)
    db_session.flush()
    return user


def is_target_container_running() -> bool:
    """Check if the disposable target container is running and listening."""
    import subprocess

    res = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "name=opsforge-disposable-target",
            "--format",
            "{{.Status}}",
        ],
        capture_output=True,
        text=True,
    )
    return "Up" in res.stdout


@pytest.fixture(scope="session")
def target_container():
    """Ensure disposable target container is up for integration tests."""
    import subprocess
    import time

    if not is_target_container_running():
        compose_file = os.path.join(
            os.path.dirname(__file__), "../docker-compose.target.yml"
        )
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "up", "-d"], capture_output=True
        )
        for _ in range(20):
            if is_target_container_running():
                time.sleep(1)
                break
            time.sleep(0.5)
    return is_target_container_running()

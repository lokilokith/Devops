"""Concurrency tests for Expiration Service against PostgreSQL."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select as sa_select

from app.checkout.exceptions import CheckoutError, InvalidCheckoutStateError
from app.checkout.models import CredentialLease, LeaseStatus
from app.checkout.repository import CredentialLeaseRepository
from app.checkout.service import CheckoutService
from app.extensions import db
from app.resources.models import Criticality, Environment, Resource, ResourceStatus, ResourceType
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretFactory, SecretMetadata, SecretVersion, SecretStatus
from app.vault.kms_factory import KMSProviderFactory
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.identity.models import User, UserStatus
from app.authorization.service import AuthorizationService
from app.identity.repository import IdentityRepository
from app.auth.service import AuthService
from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.workers.rotation_worker import _process_policy
from app.vault.exceptions import ConcurrencyError
from app.shared.database import db
from sqlalchemy import text as sa_text
from app.audit.models import AuditLog


@pytest.fixture(autouse=True)
def teardown_concurrency_data():
    """Ensure data committed by separate connections is cleaned up to prevent test pollution."""
    yield
    engine = db.session.get_bind()
    with engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM audit_logs"))
        conn.execute(sa_text("DELETE FROM credential_leases"))
        conn.execute(sa_text("DELETE FROM access_requests"))
        conn.execute(sa_text("DELETE FROM secret_rotation_policies"))
        conn.execute(sa_text("DELETE FROM vault_secret_versions"))
        conn.execute(sa_text("DELETE FROM vault_secrets"))
        conn.execute(sa_text("DELETE FROM resources WHERE resource_code LIKE 'RES_%'"))
        conn.execute(sa_text("DELETE FROM users WHERE username LIKE 'user_%'"))


def _new_sessions():
    engine = db.session.get_bind()
    Session = sessionmaker(bind=engine)
    return Session(), Session()


def _setup_service(session, app):
    lease_repo = CredentialLeaseRepository(session)
    vault_repo = SqlAlchemyVaultRepository(session)
    policy_repo = SecretRotationPolicyRepository(session)

    from app.access_requests.repository import AccessRequestRepository
    ar_repo = AccessRequestRepository(session)
    audit_repo = AuditRepository(session)
    audit_service = AuditService(audit_repo)

    kms_provider = KMSProviderFactory.resolve_active_provider(session)
    encryption_service = EncryptionService(kms_provider)

    identity_repo = IdentityRepository(session)
    auth_service = AuthService(identity_repo)
    authz_service = AuthorizationService(session)

    return CheckoutService(
        session=session,
        lease_repo=lease_repo,
        vault_repo=vault_repo,
        policy_repo=policy_repo,
        ar_repo=ar_repo,
        audit_service=audit_service,
        authz_service=authz_service,
        encryption_service=encryption_service,
    )


def _setup_test_data(session):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        employee_id=f"EMP_{uuid.uuid4().hex[:6]}",
        username=f"user_{uuid.uuid4().hex[:6]}",
        email=f"user_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Test User",
        status=UserStatus.ACTIVE,
    )
    session.add(user)

    uid = uuid.uuid4().hex[:6]
    resource = Resource(
        resource_code=f"RES_{uid}",
        resource_name=f"Resource {uid}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    session.add(resource)
    session.flush()

    secret = SecretFactory.create_new_secret(resource.id)
    meta = SecretMetadata("v1", "AES", "nonce", {"r": str(resource.id)})
    sv = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=b"dek",
        encrypted_payload=b"payload",
        metadata=meta,
        created_at=datetime.now(timezone.utc),
        created_by=user_id
    )
    secret.add_version(sv)

    repo = SqlAlchemyVaultRepository(session)
    repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=user_id,
        requested_resource_id=resource.id,
        status=AccessRequestStatus.APPROVED,
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
        business_justification="test"
    )
    session.add(ar)
    session.commit()

    return user, resource, secret, ar


def test_expiration_vs_checkin_concurrency(app):
    """Race condition between Expiration Worker and manual Check-in."""
    sess_a, sess_b = _new_sessions()

    user, resource, secret, ar = _setup_test_data(sess_a)
    svc_a = _setup_service(sess_a, app)
    svc_b = _setup_service(sess_b, app)

def test_expiration_vs_checkin_concurrency(app):
    """Race condition between Expiration Worker and manual Check-in."""
    sess_a, sess_b = _new_sessions()

    user, resource, secret, ar = _setup_test_data(sess_a)
    svc_a = _setup_service(sess_a, app)
    svc_b = _setup_service(sess_b, app)

    svc_a._crypto.decrypt_payload = lambda *args, **kwargs: b"secret"
    svc_a.checkout(user.id, ar.id)
    sess_a.commit()

    lease = CredentialLeaseRepository(sess_a).get_active_leases_for_user(user.id)[0]
    lease.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sess_a.commit()

    # Take snapshots for B to use
    sess_b.expire_all()
    b_lease = CredentialLeaseRepository(sess_b).get_by_id(lease.id)
    b_secret = SqlAlchemyVaultRepository(sess_b).find_by_id(secret.id)

    # A executes and commits
    svc_a.expire(lease.id)
    sess_a.commit()

    # B executes with stale data
    svc_b._lease_repo.get_by_id = lambda lid: b_lease
    svc_b._vault_repo.find_by_id = lambda sid: b_secret

    with pytest.raises(InvalidCheckoutStateError):
        svc_b.checkin(user.id, lease.id)
        sess_b.commit()

    sess_a.expire_all()
    final_lease = CredentialLeaseRepository(sess_a).get_by_id(lease.id)
    assert final_lease.status == LeaseStatus.EXPIRED

    final_secret = SqlAlchemyVaultRepository(sess_a).find_by_id(secret.id)
    assert final_secret.status == SecretStatus.ROTATING


def test_expiration_vs_revoke_concurrency(app):
    """Race condition between Expiration Worker and Admin Revoke."""
    sess_a, sess_b = _new_sessions()

    user, resource, secret, ar = _setup_test_data(sess_a)
    svc_a = _setup_service(sess_a, app)
    svc_b = _setup_service(sess_b, app)

    svc_a._crypto.decrypt_payload = lambda *args, **kwargs: b"secret"
    svc_a.checkout(user.id, ar.id)
    sess_a.commit()

    lease = CredentialLeaseRepository(sess_a).get_active_leases_for_user(user.id)[0]
    lease.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sess_a.commit()

    # Take snapshots for B to use
    sess_b.expire_all()
    b_lease = CredentialLeaseRepository(sess_b).get_by_id(lease.id)
    b_secret = SqlAlchemyVaultRepository(sess_b).find_by_id(secret.id)

    admin_id = uuid.uuid4()

    # Mock authorization for the test
    svc_a._authz.authorize = lambda *args, **kwargs: None
    svc_b._authz.authorize = lambda *args, **kwargs: None

    # A executes and commits (revoke)
    svc_a.revoke(admin_id, lease.id)
    sess_a.commit()

    # B executes with stale data (expire)
    svc_b._lease_repo.get_by_id = lambda lid: b_lease
    svc_b._vault_repo.find_by_id = lambda sid: b_secret

    with pytest.raises(InvalidCheckoutStateError):
        svc_b.expire(lease.id)
        sess_b.commit()

    sess_a.expire_all()
    final_lease = CredentialLeaseRepository(sess_a).get_by_id(lease.id)
    assert final_lease.status == LeaseStatus.REVOKED
    final_secret = SqlAlchemyVaultRepository(sess_a).find_by_id(secret.id)
    assert final_secret.status == SecretStatus.ROTATING


def test_expiration_worker_vs_expiration_worker_concurrency(app):
    """Race condition between two Expiration Workers processing the same lease."""
    sess_a, sess_b = _new_sessions()

    user, resource, secret, ar = _setup_test_data(sess_a)
    svc_a = _setup_service(sess_a, app)
    svc_b = _setup_service(sess_b, app)

    svc_a._crypto.decrypt_payload = lambda *args, **kwargs: b"secret"
    svc_a.checkout(user.id, ar.id)
    sess_a.commit()

    lease = CredentialLeaseRepository(sess_a).get_active_leases_for_user(user.id)[0]
    lease.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sess_a.commit()

    # Take snapshots for B to use
    sess_b.expire_all()
    b_lease = CredentialLeaseRepository(sess_b).get_by_id(lease.id)
    b_secret = SqlAlchemyVaultRepository(sess_b).find_by_id(secret.id)

    # A executes and commits (expire)
    svc_a.expire(lease.id)
    sess_a.commit()

    # B executes with stale data (expire)
    svc_b._lease_repo.get_by_id = lambda lid: b_lease
    svc_b._vault_repo.find_by_id = lambda sid: b_secret

    with pytest.raises(InvalidCheckoutStateError):
        svc_b.expire(lease.id)
        sess_b.commit()

    sess_a.expire_all()
    final_lease = CredentialLeaseRepository(sess_a).get_by_id(lease.id)
    assert final_lease.status == LeaseStatus.EXPIRED

    # Audit log should only have one EXPIRED event
    logs = sess_a.execute(sa_select(AuditLog).where(
        AuditLog.action == "LEASE_EXPIRED",
        AuditLog.resource_id == str(lease.id)
    )).scalars().all()
    assert len(logs) == 1


def test_expiration_vs_rotation_concurrency(app):
    """Race condition where Expiration and Rotation overlap."""
    sess_a, sess_b = _new_sessions()

    user, resource, secret, ar = _setup_test_data(sess_a)

    from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus
    policy = SecretRotationPolicy(
        id=uuid.uuid4(),
        vault_secret_id=secret.id,
        plugin_name="manual",
        rotation_interval_days=30,
        rotation_interval_seconds=30*86400,
        status=RotationStatus.ACTIVE,
        next_rotation_at=datetime.now(timezone.utc) - timedelta(days=1),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        retry_count=0
    )
    sess_a.add(policy)

    svc_a = _setup_service(sess_a, app)
    svc_a._crypto.decrypt_payload = lambda *args, **kwargs: b"secret"
    svc_a.checkout(user.id, ar.id)
    sess_a.commit()

    lease = CredentialLeaseRepository(sess_a).get_active_leases_for_user(user.id)[0]
    lease.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sess_a.commit()

    from app.workers.rotation_worker import _fetch_eligible_policies
    from app.vault.models import VaultSecret

    # Refresh sess_b so it sees the latest DB state
    sess_b.expire_all()

    # 1. Rotation worker sees eligible policy?
    # But wait, CHECKED_OUT secret is excluded by rotation query!
    # So rotation worker fetches eligible policies and gets nothing.

    # Debug: Check secret status in DB from sess_b
    db_secret = sess_b.execute(sa_select(VaultSecret).where(VaultSecret.id == secret.id)).scalar_one()
    print(f"\nDEBUG My Secret ID: {secret.id}")
    print(f"DEBUG DB Secret Status: {db_secret.status}")

    from sqlalchemy.dialects import postgresql
    now = datetime.now(timezone.utc)
    from app.vault_lifecycle.models import RotationStatus
    from app.vault.domain import SecretStatus
    stmt = (
        sa_select(SecretRotationPolicy)
        .join(VaultSecret, SecretRotationPolicy.vault_secret_id == VaultSecret.id)
        .where(
            SecretRotationPolicy.status == RotationStatus.ACTIVE,
            SecretRotationPolicy.next_rotation_at <= now,
            VaultSecret.status != SecretStatus.CHECKED_OUT,
        )
    )
    print("DEBUG SQL:", str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))

    policies = _fetch_eligible_policies(sess_b)
    # Filter to only the policy we care about to avoid cross-test pollution
    policies = [p for p in policies if p.vault_secret_id == secret.id]
    print(f"DEBUG Policies found for this secret: {len(policies)}")
    if policies:
        print(f"DEBUG Policy Secret ID: {policies[0].vault_secret_id}")

    assert len(policies) == 0

    # 2. Expiration worker expires it
    svc_a.expire(lease.id)
    sess_a.commit()

    # 3. Now rotation worker fetches again and gets it
    policies2 = _fetch_eligible_policies(sess_b)
    policies2 = [p for p in policies2 if p.vault_secret_id == secret.id]
    assert len(policies2) == 1

    assert policies2[0].id == policy.id

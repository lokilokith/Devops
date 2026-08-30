"""Concurrency tests for Checkout Service."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.auth.service import AuthService
from app.checkout.exceptions import InvalidCheckoutStateError
from app.checkout.repository import CredentialLeaseRepository
from app.checkout.service import CheckoutService
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository
from app.platform.extensions import db
from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretFactory, SecretMetadata, SecretVersion
from app.vault.kms_factory import KMSProviderFactory
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.repository import SecretRotationPolicyRepository


@pytest.fixture(autouse=True)
def teardown_concurrency_data():
    """Ensure data committed by separate connections is cleaned up to prevent test pollution."""
    yield
    engine = db.session.get_bind()
    with engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM audit_logs"))
        conn.execute(sa_text("DELETE FROM credential_leases"))
        conn.execute(sa_text("DELETE FROM access_requests"))
        conn.execute(sa_text("DELETE FROM vault_secret_versions"))
        conn.execute(sa_text("DELETE FROM vault_secrets"))
        conn.execute(
            sa_text("DELETE FROM resources WHERE resource_code LIKE 'RES03_%'")
        )
        conn.execute(
            sa_text(
                "DELETE FROM users WHERE username LIKE 'user_a_%' OR username LIKE 'user_b_%'"
            )
        )


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
    _auth_service = AuthService(identity_repo)  # noqa: F841

    from unittest.mock import MagicMock

    from app.policy_engine.decisions import PolicyDecision

    mock_authz = MagicMock()
    mock_authz.authorize.return_value = None

    mock_policy_engine = MagicMock()
    mock_policy_engine.evaluate_vault_retrieval.return_value = PolicyDecision.ALLOW

    return CheckoutService(
        session=session,
        lease_repo=lease_repo,
        vault_repo=vault_repo,
        policy_repo=policy_repo,
        ar_repo=ar_repo,
        audit_service=audit_service,
        authz_service=mock_authz,
        encryption_service=encryption_service,
        policy_engine=mock_policy_engine,
    )


def test_concurrent_checkout(app):
    """Gate: two users checkout simultaneously -> 1 success, 1 ConcurrencyError."""
    sess_a, sess_b = _new_sessions()

    # Setup resource and secret
    # Create users first
    user_id_a = uuid.uuid4()
    user_a = User(
        id=user_id_a,
        employee_id=f"EMP_{uuid.uuid4().hex[:6]}",
        username=f"user_a_{uuid.uuid4().hex[:6]}",
        email=f"a_{uuid.uuid4().hex[:6]}@test.com",
        full_name="User A",
        status=UserStatus.ACTIVE,
    )
    user_id_b = uuid.uuid4()
    user_b = User(
        id=user_id_b,
        employee_id=f"EMP_{uuid.uuid4().hex[:6]}",
        username=f"user_b_{uuid.uuid4().hex[:6]}",
        email=f"b_{uuid.uuid4().hex[:6]}@test.com",
        full_name="User B",
        status=UserStatus.ACTIVE,
    )
    sess_a.add(user_a)
    sess_a.add(user_b)
    sess_a.flush()

    uid = uuid.uuid4().hex[:6]
    resource = Resource(
        resource_code=f"RES03_{uid}",
        resource_name=f"Concurrency Resource {uid}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    sess_a.add(resource)
    sess_a.flush()
    secret = SecretFactory.create_new_secret(resource.id)

    # Add a version so we can checkout
    meta = SecretMetadata("v1", "AES", "nonce", {"r": str(resource.id)})
    sv = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=b"dek",
        encrypted_payload=b"payload",
        metadata=meta,
        created_at=datetime.now(timezone.utc),
        created_by=user_id_a,
    )
    secret.add_version(sv)

    repo = SqlAlchemyVaultRepository(sess_a)
    repo.save(secret)
    sess_a.commit()

    # Create Access Requests
    ar_a = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=user_id_a,
        requested_resource_id=resource.id,
        status=AccessRequestStatus.APPROVED,
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
        business_justification="test A",
    )
    ar_b = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=user_id_b,
        requested_resource_id=resource.id,
        status=AccessRequestStatus.APPROVED,
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
        business_justification="test B",
    )
    sess_a.add(ar_a)
    sess_a.add(ar_b)
    sess_a.commit()

    # Initialize services
    svc_a = _setup_service(sess_a, app)
    svc_b = _setup_service(sess_b, app)

    # We need to simulate the exact race. We pause right before CAS.
    # In Python, we can't easily pause inside without mocking, but we can do it by loading
    # the exact same row_version.

    # Session A checkout
    # Session A is fast and completes
    # We will mock the decryption to avoid needing a real KMS setup for both
    class MockCrypto:
        def decrypt_payload(self, *args, **kwargs):
            return b"secret_password"

    svc_a._crypto = MockCrypto()
    svc_b._crypto = MockCrypto()

    # Session A completes
    plaintext = svc_a.checkout(user_id_a, ar_a.id)
    assert plaintext == b"secret_password"

    # Session B attempts to checkout the same secret.
    # But wait, if Session B queries it now, it will see it's CHECKED_OUT and raise InvalidCheckoutStateError.
    # To simulate a race, we have to bypass the status check in Session B manually or rely on row_version mismatch.
    # Actually, in a real race, B reads status = ACTIVE, A reads status = ACTIVE, A CAS succeeds, B CAS fails.
    # We can simulate B's race by forcing B's read of the secret to return the OLD secret object.

    # Let's mock `_vault_repo.find_by_resource` in svc_b to return the OLD secret (status=ACTIVE, row_version=1)
    old_secret = SecretFactory.create_new_secret(resource.id)
    old_secret.id = secret.id

    def mock_find_by_resource(res_id):
        return old_secret

    svc_b._vault_repo.find_by_resource = mock_find_by_resource

    # Now when svc_b tries to CAS save, it expects row_version=1, but DB has row_version=2.
    with pytest.raises(InvalidCheckoutStateError, match="Checkout conflict"):
        svc_b.checkout(user_id_b, ar_b.id)

    # Verify only ONE lease was created and is ACTIVE
    final_repo = CredentialLeaseRepository(db.session)
    leases = final_repo.get_active_leases_for_user(user_id_a)
    assert len(leases) == 1
    leases_b = final_repo.get_active_leases_for_user(user_id_b)
    assert len(leases_b) == 0

    sess_a.close()
    sess_b.close()

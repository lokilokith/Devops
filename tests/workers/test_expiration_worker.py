"""ExpirationWorker tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.checkout.models import CredentialLease, LeaseStatus
from app.checkout.repository import CredentialLeaseRepository
from app.checkout.service import CheckoutService
from app.resources.models import Criticality, Environment, Resource, ResourceStatus, ResourceType
from app.vault.domain import SecretFactory, SecretStatus
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.workers.expiration_worker import run_expiration_job


def _make_resource(db_session) -> Resource:
    resource = Resource(
        resource_code=f"WRK{uuid.uuid4().hex[:6].upper()}",
        resource_name=f"Worker Test Resource {uuid.uuid4().hex[:8]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    db_session.flush()
    return resource


def _make_secret(db_session, resource: Resource):
    repo = SqlAlchemyVaultRepository(db_session)
    secret = SecretFactory.create_new_secret(resource.id)
    repo.save(secret)
    db_session.flush()
    return secret


def _make_policy(db_session, secret_id: uuid.UUID):
    now = datetime.now(timezone.utc)
    policy = SecretRotationPolicy(
        vault_secret_id=secret_id,
        plugin_name="stub",
        rotation_interval_days=30,
        rotation_interval_seconds=2592000,
        retry_count=0,
        last_rotated_at=None,
        next_rotation_at=now - timedelta(days=1),
        status=RotationStatus.ACTIVE,
    )
    db_session.add(policy)
    db_session.flush()
    return policy


def _make_ar(db_session, user_id: uuid.UUID, resource_id: uuid.UUID) -> uuid.UUID:
    from app.access_requests.models import AccessRequest, AccessRequestStatus
    now = datetime.now(timezone.utc)
    ar = AccessRequest(
        request_number=f"REQ-{uuid.uuid4().hex[:6].upper()}",
        requester_id=user_id,
        requested_resource_id=resource_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test",
        requested_end=now + timedelta(days=1)
    )
    db_session.add(ar)
    db_session.flush()
    return ar.id


def _make_lease(db_session, secret_id: uuid.UUID, user_id: uuid.UUID, ar_id: uuid.UUID, *, expired: bool = False, status: LeaseStatus = LeaseStatus.ACTIVE):
    now = datetime.now(timezone.utc)
    expires_at = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    lease = CredentialLease(
        vault_secret_id=secret_id,
        user_id=user_id,
        access_request_id=ar_id,
        expires_at=expires_at,
        status=status,
    )
    db_session.add(lease)
    db_session.flush()
    return lease


@pytest.fixture
def checkout_svc(db_session):
    from app.access_requests.repository import AccessRequestRepository
    from app.vault.crypto import EncryptionService, LocalKMSProvider

    lease_repo = CredentialLeaseRepository(db_session)
    vault_repo = SqlAlchemyVaultRepository(db_session)
    policy_repo = SecretRotationPolicyRepository(db_session)
    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)
    ar_repo = AccessRequestRepository(db_session)
    kms_provider = LocalKMSProvider()
    encryption_service = EncryptionService(kms_provider)

    class MockAuthz:
        def enforce(self, *args, **kwargs): pass
        def has_permission(self, *args, **kwargs): return True

    return CheckoutService(
        session=db_session,
        lease_repo=lease_repo,
        vault_repo=vault_repo,
        policy_repo=policy_repo,
        ar_repo=ar_repo,
        audit_service=audit_svc,
        authz_service=MockAuthz(),
        encryption_service=encryption_service,
    )


def test_expired_active_lease_is_processed(db_session, checkout_svc, test_user):
    res = _make_resource(db_session)
    sec = _make_secret(db_session, res)
    _make_policy(db_session, sec.id)
    sec.checkout()
    SqlAlchemyVaultRepository(db_session).save(sec)
    db_session.flush()

    ar_id = _make_ar(db_session, test_user.id, res.id)
    lease = _make_lease(db_session, sec.id, test_user.id, ar_id, expired=True)

    result = run_expiration_job(db_session, checkout_svc)

    assert result["attempted"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0

    db_session.expire_all()
    fresh_lease = db_session.execute(select(CredentialLease).where(CredentialLease.id == lease.id)).scalar()
    assert fresh_lease.status == LeaseStatus.EXPIRED


def test_non_expired_lease_untouched(db_session, checkout_svc, test_user):
    res = _make_resource(db_session)
    sec = _make_secret(db_session, res)
    _make_policy(db_session, sec.id)
    sec.checkout()
    SqlAlchemyVaultRepository(db_session).save(sec)
    db_session.flush()

    ar_id = _make_ar(db_session, test_user.id, res.id)
    lease = _make_lease(db_session, sec.id, test_user.id, ar_id, expired=False)

    result = run_expiration_job(db_session, checkout_svc)

    assert result["attempted"] == 0
    assert result["succeeded"] == 0


def test_terminal_lease_untouched(db_session, checkout_svc, test_user):
    res = _make_resource(db_session)
    sec = _make_secret(db_session, res)
    _make_policy(db_session, sec.id)

    # Not checked out, just a past terminal lease
    ar_id = _make_ar(db_session, test_user.id, res.id)
    lease = _make_lease(db_session, sec.id, test_user.id, ar_id, expired=True, status=LeaseStatus.RETURNED)

    result = run_expiration_job(db_session, checkout_svc)

    assert result["attempted"] == 0
    assert result["succeeded"] == 0


def test_secret_state_changes_correctly_after_expiration(db_session, checkout_svc, test_user):
    res = _make_resource(db_session)
    sec = _make_secret(db_session, res)
    _make_policy(db_session, sec.id)
    sec.checkout()
    SqlAlchemyVaultRepository(db_session).save(sec)
    db_session.flush()

    ar_id = _make_ar(db_session, test_user.id, res.id)
    _make_lease(db_session, sec.id, test_user.id, ar_id, expired=True)

    run_expiration_job(db_session, checkout_svc)

    db_session.expire_all()
    fresh_sec = SqlAlchemyVaultRepository(db_session).find_by_id(sec.id)
    assert fresh_sec.status == SecretStatus.ROTATING


def test_multiple_leases_process_independently(db_session, checkout_svc, test_user):
    res1 = _make_resource(db_session)
    sec1 = _make_secret(db_session, res1)
    _make_policy(db_session, sec1.id)
    sec1.checkout()
    SqlAlchemyVaultRepository(db_session).save(sec1)

    res2 = _make_resource(db_session)
    sec2 = _make_secret(db_session, res2)
    _make_policy(db_session, sec2.id)
    sec2.checkout()
    SqlAlchemyVaultRepository(db_session).save(sec2)
    db_session.flush()

    ar_id1 = _make_ar(db_session, test_user.id, res1.id)
    ar_id2 = _make_ar(db_session, test_user.id, res2.id)
    lease1 = _make_lease(db_session, sec1.id, test_user.id, ar_id1, expired=True)
    lease2 = _make_lease(db_session, sec2.id, test_user.id, ar_id2, expired=True)

    # Force lease2 to fail by patching checkout_svc.expire to raise if id == lease2.id
    original_expire = checkout_svc.expire
    def fake_expire(lease_id):
        if lease_id == lease2.id:
            raise RuntimeError("Fake failure")
        return original_expire(lease_id)

    with patch.object(checkout_svc, 'expire', side_effect=fake_expire):
        result = run_expiration_job(db_session, checkout_svc)

    assert result["attempted"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1

    db_session.expire_all()
    fresh_lease1 = db_session.execute(select(CredentialLease).where(CredentialLease.id == lease1.id)).scalar()
    fresh_lease2 = db_session.execute(select(CredentialLease).where(CredentialLease.id == lease2.id)).scalar()

    assert fresh_lease1.status == LeaseStatus.EXPIRED
    assert fresh_lease2.status == LeaseStatus.ACTIVE

"""Checkout Service unit tests."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.authorization.exceptions import AuthorizationDeniedError
from app.checkout.exceptions import (
    CheckoutError,
    InvalidCheckoutStateError,
    PolicyDeniedError,
    UnauthorizedCheckoutError,
)
from app.checkout.models import CredentialLease, LeaseStatus
from app.checkout.repository import CredentialLeaseRepository
from app.checkout.service import CheckoutService
from app.policy_engine.decisions import PolicyDecision
from app.resources.models import Criticality, Environment, Resource, ResourceType
from app.vault.domain import SecretFactory, SecretStatus, SecretVersion
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository


@pytest.fixture
def mock_policy_engine():
    engine = MagicMock()
    engine.evaluate_vault_retrieval.return_value = PolicyDecision.ALLOW
    return engine


@pytest.fixture
def checkout_service(db_session, app, mock_policy_engine):
    from unittest.mock import MagicMock

    from app.access_requests.repository import AccessRequestRepository
    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.vault.crypto import EncryptionService
    from app.vault.kms_factory import KMSProviderFactory

    mock_authz = MagicMock()
    mock_authz.authorize.return_value = None

    lease_repo = CredentialLeaseRepository(db_session)
    vault_repo = SqlAlchemyVaultRepository(db_session)
    policy_repo = SecretRotationPolicyRepository(db_session)
    ar_repo = AccessRequestRepository(db_session)
    audit_repo = AuditRepository(db_session)
    audit_service = AuditService(audit_repo)

    kms_provider = KMSProviderFactory.resolve_active_provider(db_session)
    encryption_service = EncryptionService(kms_provider)

    return CheckoutService(
        session=db_session,
        lease_repo=lease_repo,
        vault_repo=vault_repo,
        policy_repo=policy_repo,
        ar_repo=ar_repo,
        audit_service=audit_service,
        authz_service=mock_authz,
        encryption_service=encryption_service,
        policy_engine=mock_policy_engine,
    )


def test_checkout_success(db_session, checkout_service, normal_user):
    # Setup Resource
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name=f"Test Res {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)

    # Setup Secret
    secret = SecretFactory.create_new_secret(res_id)

    # Add a version so we can decrypt
    encrypted_dek, encrypted_payload, meta = checkout_service._crypto.encrypt_payload(
        res_id, secret.id, b"secret_password"
    )

    sv = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=encrypted_dek,
        encrypted_payload=encrypted_payload,
        metadata=meta,
        created_at=datetime.now(timezone.utc),
        created_by=normal_user.id,
    )
    secret.add_version(sv)
    checkout_service._vault_repo.save(secret)

    # Setup Access Request
    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
        business_justification="test checkout",
    )
    db_session.add(ar)
    db_session.flush()

    # Perform Checkout
    plaintext = checkout_service.checkout(normal_user.id, ar.id)
    assert plaintext == b"secret_password"

    # Verify State
    updated_secret = checkout_service._vault_repo.find_by_id(secret.id)
    assert updated_secret.status == SecretStatus.CHECKED_OUT

    lease = checkout_service._lease_repo.get_active_lease_for_secret(secret.id)
    assert lease is not None
    assert lease.status == LeaseStatus.ACTIVE
    assert lease.user_id == normal_user.id


def test_checkin_success(db_session, checkout_service, normal_user):
    # Setup Resource, Secret, Lease, Policy
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name=f"Test Res {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)

    secret = SecretFactory.create_new_secret(res_id)
    secret.status = SecretStatus.CHECKED_OUT
    checkout_service._vault_repo.save(secret)

    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=3600,
        next_rotation_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    checkout_service._policy_repo.save(policy)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test checkin",
    )
    db_session.add(ar)

    lease = CredentialLease(
        vault_secret_id=secret.id,
        user_id=normal_user.id,
        access_request_id=ar.id,
        status=LeaseStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    checkout_service._lease_repo.save(lease)
    db_session.flush()

    # Perform Check-in
    checkout_service.checkin(normal_user.id, lease.id)

    # Verify State
    updated_lease = checkout_service._lease_repo.get_by_id(lease.id)
    assert updated_lease.status == LeaseStatus.RETURNED

    updated_secret = checkout_service._vault_repo.find_by_id(secret.id)
    assert updated_secret.status == SecretStatus.ROTATING

    updated_policy = checkout_service._policy_repo.get_by_vault_secret_id(secret.id)
    assert updated_policy.next_rotation_at <= datetime.now(timezone.utc)


def test_expired_request_cannot_checkout(db_session, checkout_service, normal_user):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name=f"Test Res {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        requested_end=datetime.now(timezone.utc) - timedelta(hours=1),
        business_justification="test",
    )
    db_session.add(ar)
    db_session.flush()

    with pytest.raises(
        InvalidCheckoutStateError, match="Access request window has expired"
    ):
        checkout_service.checkout(normal_user.id, ar.id)


def test_expiration_triggers_rotation(db_session, checkout_service, normal_user):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name=f"Test Res {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)

    secret = SecretFactory.create_new_secret(res_id)
    secret.status = SecretStatus.CHECKED_OUT
    checkout_service._vault_repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test checkin",
    )
    db_session.add(ar)

    lease = CredentialLease(
        vault_secret_id=secret.id,
        user_id=normal_user.id,
        access_request_id=ar.id,
        status=LeaseStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    checkout_service._lease_repo.save(lease)
    db_session.flush()

    attempted, count = checkout_service.process_expirations()
    assert count >= 1

    updated_lease = checkout_service._lease_repo.get_by_id(lease.id)
    assert updated_lease.status == LeaseStatus.EXPIRED

    updated_secret = checkout_service._vault_repo.find_by_id(secret.id)
    assert updated_secret.status == SecretStatus.ROTATING


def test_checkout_rbac_denied(db_session, checkout_service, normal_user):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name="Test",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    secret = SecretFactory.create_new_secret(res_id)
    checkout_service._vault_repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test",
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ar)
    db_session.flush()

    checkout_service._authz.authorize.side_effect = AuthorizationDeniedError(
        "RBAC Denied"
    )

    with pytest.raises(
        UnauthorizedCheckoutError,
        match="User lacks RBAC permission to checkout Vault secrets.",
    ):
        checkout_service.checkout(normal_user.id, ar.id)


def test_checkout_policy_deny(db_session, checkout_service, normal_user):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name="Test",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    secret = SecretFactory.create_new_secret(res_id)
    checkout_service._vault_repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test",
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ar)
    db_session.flush()

    checkout_service._policy_engine.evaluate_vault_retrieval.return_value = (
        PolicyDecision.DENY
    )

    with pytest.raises(
        PolicyDeniedError, match="Checkout explicitly denied by policy."
    ):
        checkout_service.checkout(normal_user.id, ar.id)


def test_checkout_policy_require_approval(db_session, checkout_service, normal_user):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name="Test",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    secret = SecretFactory.create_new_secret(res_id)
    checkout_service._vault_repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test",
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ar)
    db_session.flush()

    checkout_service._policy_engine.evaluate_vault_retrieval.return_value = (
        PolicyDecision.REQUIRE_APPROVAL
    )

    with pytest.raises(
        PolicyDeniedError,
        match="Policy requires approval but the provided request did not satisfy the policy engine.",
    ):
        checkout_service.checkout(normal_user.id, ar.id)


def test_checkout_policy_exception_fails_closed(
    db_session, checkout_service, normal_user
):
    res_id = uuid.uuid4()
    resource = Resource(
        id=res_id,
        resource_code=f"RES_{uuid.uuid4().hex[:6]}",
        resource_name="Test",
        resource_type=ResourceType.SERVER,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    secret = SecretFactory.create_new_secret(res_id)
    checkout_service._vault_repo.save(secret)

    ar = AccessRequest(
        id=uuid.uuid4(),
        request_number=f"REQ_{uuid.uuid4().hex[:6]}",
        requester_id=normal_user.id,
        requested_resource_id=res_id,
        status=AccessRequestStatus.APPROVED,
        business_justification="test",
        requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ar)
    db_session.flush()

    checkout_service._policy_engine.evaluate_vault_retrieval.side_effect = ValueError(
        "Unexpected engine failure"
    )

    with pytest.raises(CheckoutError, match="Policy evaluation failed"):
        checkout_service.checkout(normal_user.id, ar.id)

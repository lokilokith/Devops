from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.vault.domain import (
    SecretDomainService,
    SecretFactory,
    SecretMetadata,
    SecretStatus,
    SecretVersion,
)


def test_secret_factory_creates_valid_secret():
    resource_id = uuid4()
    secret = SecretFactory.create_new_secret(resource_id)

    assert secret.resource_id == resource_id
    assert secret.status == SecretStatus.ACTIVE
    assert secret.current_version_id is None
    assert secret.row_version == 1
    assert len(secret.versions) == 0

def test_secret_add_version():
    secret = SecretFactory.create_new_secret(uuid4())
    version_id = uuid4()

    metadata = SecretMetadata(
        key_version="v1",
        algorithm="AES-256-GCM",
        nonce="testnonce",
        encryption_context={"resource_id": str(secret.resource_id)}
    )

    version = SecretVersion(
        id=version_id,
        secret_id=secret.id,
        encrypted_dek=b"encdek",
        encrypted_payload=b"encpayload",
        metadata=metadata,
        created_at=datetime.now(timezone.utc),
        created_by=uuid4()
    )

    secret.add_version(version)

    assert secret.current_version_id == version_id
    assert secret.row_version == 2
    assert len(secret.versions) == 1

    assert secret.get_current_version() == version

def test_add_version_wrong_secret_id():
    secret = SecretFactory.create_new_secret(uuid4())
    version = SecretVersion(
        id=uuid4(),
        secret_id=uuid4(), # Wrong ID
        encrypted_dek=b"",
        encrypted_payload=b"",
        metadata=SecretMetadata("v1", "AES", "n", {}),
        created_at=datetime.now(timezone.utc),
        created_by=uuid4()
    )

    with pytest.raises(ValueError):
        secret.add_version(version)

def test_secret_disable():
    secret = SecretFactory.create_new_secret(uuid4())
    assert secret.row_version == 1

    secret.disable()
    assert secret.status == SecretStatus.DISABLED
    assert secret.row_version == 2

def test_domain_service_ensure_can_rotate():
    secret = SecretFactory.create_new_secret(uuid4())
    SecretDomainService.ensure_can_rotate(secret) # Should not raise

    secret.disable()
    with pytest.raises(ValueError):
        SecretDomainService.ensure_can_rotate(secret)

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.domain import SecretFactory, SecretMetadata, SecretVersion
from app.vault.exceptions import ConcurrencyError
from app.vault.repository import SqlAlchemyVaultRepository


def test_repository_mapping_cycle(db_session, test_user):
    """Verifies Domain -> DB -> Domain mapping preserves all attributes."""
    repo = SqlAlchemyVaultRepository(db_session)

    resource = Resource(resource_code="TST01", resource_name="Test Resource", resource_type=ResourceType.SERVER, status=ResourceStatus.ACTIVE, environment=Environment.DEV, criticality=Criticality.LOW)
    db_session.add(resource)
    db_session.commit()

    # 1. Create Domain Object
    secret = SecretFactory.create_new_secret(resource.id)

    metadata = SecretMetadata(
        key_version="v1",
        algorithm="AES-256-GCM",
        nonce="nonce123",
        encryption_context={"resource_id": str(resource.id)}
    )

    version_id = uuid4()
    version = SecretVersion(
        id=version_id,
        secret_id=secret.id,
        encrypted_dek=b"dek_bytes",
        encrypted_payload=b"payload_bytes",
        metadata=metadata,
        created_at=datetime.now(timezone.utc),
        created_by=test_user.id
    )
    secret.add_version(version)

    # 2. Save to DB
    repo.save(secret)
    db_session.commit()

    # 3. Load from DB
    db_session.expunge_all() # Ensure we load fresh from DB
    loaded = repo.find_by_id(secret.id)

    # 4. Verify Equivalent Domain Object
    assert loaded is not None
    assert loaded.id == secret.id
    assert loaded.resource_id == secret.resource_id
    assert loaded.status == secret.status
    assert loaded.current_version_id == secret.current_version_id
    assert loaded.row_version == secret.row_version

    assert len(loaded.versions) == 1
    loaded_version = loaded.versions[0]
    assert loaded_version.id == version.id
    assert loaded_version.encrypted_dek == b"dek_bytes"
    assert loaded_version.encrypted_payload == b"payload_bytes"
    assert loaded_version.created_by == test_user.id

    assert loaded_version.metadata.key_version == "v1"
    assert loaded_version.metadata.algorithm == "AES-256-GCM"
    assert loaded_version.metadata.encryption_context == {"resource_id": str(resource.id)}


def test_optimistic_locking_conflict(db_session, test_user):
    repo = SqlAlchemyVaultRepository(db_session)

    resource = Resource(resource_code="TST02", resource_name="Test Resource 2", resource_type=ResourceType.SERVER, status=ResourceStatus.ACTIVE, environment=Environment.DEV, criticality=Criticality.LOW)
    db_session.add(resource)
    db_session.commit()

    secret = SecretFactory.create_new_secret(resource.id)
    repo.save(secret)
    db_session.commit()

    # Load two separate instances
    instance1 = repo.find_by_id(secret.id)

    db_session.expunge_all()
    repo2 = SqlAlchemyVaultRepository(db_session)
    instance2 = repo2.find_by_id(secret.id)

    # Modify instance 1 and save
    instance1.disable()
    repo.save(instance1)
    db_session.commit()

    # Modify instance 2 and attempt to save -> should throw ValueError
    instance2.disable()
    with pytest.raises(ConcurrencyError, match="row_version mismatch"):
        repo2.save(instance2)

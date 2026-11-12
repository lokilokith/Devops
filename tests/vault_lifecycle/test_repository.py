"""Tests for Vault Lifecycle Repository."""

import uuid
from datetime import datetime, timezone

from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository


def test_create_and_get_policy(db_session):
    from app.resources.models import (
        Criticality,
        Environment,
        Resource,
        ResourceStatus,
        ResourceType,
    )
    from app.vault.models import SecretStatus, VaultSecret

    # Needs a real vault_secret_id due to foreign key
    res = Resource(
        id=uuid.uuid4(),
        resource_name="Test Res",
        resource_code="test-res",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(res)

    secret = VaultSecret(
        id=uuid.uuid4(), resource_id=res.id, status=SecretStatus.ACTIVE, row_version=1
    )
    db_session.add(secret)
    db_session.commit()

    repo = SecretRotationPolicyRepository(db_session)
    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=3600,
        status=RotationStatus.ACTIVE,
        next_rotation_at=datetime.now(timezone.utc),
    )
    repo.save(policy)
    db_session.commit()

    fetched = repo.get_by_vault_secret_id(secret.id)
    assert fetched is not None
    assert fetched.rotation_interval_seconds == 3600
    assert fetched.status == RotationStatus.ACTIVE

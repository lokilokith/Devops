"""Integration tests for Vault Lifecycle and Vault Rotation."""

import uuid
from datetime import datetime, timezone

from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.models import (
    SecretStatus,
    VaultSecret,
)
from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository


def test_vault_rotation_updates_lifecycle_policy(db_session, client, admin_token):
    # 1. Create a Resource
    res = Resource(
        id=uuid.uuid4(),
        resource_name="Test Res E2E",
        resource_code="test-res-e2e",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(res)

    # 2. Create a Vault Secret
    secret_id = uuid.uuid4()
    secret = VaultSecret(
        id=secret_id, resource_id=res.id, status=SecretStatus.ACTIVE, row_version=1
    )
    db_session.add(secret)
    db_session.commit()
    # Active KMS config already seeded by fixture; no need to create another

    # 3. Create a SecretRotationPolicy
    repo = SecretRotationPolicyRepository(db_session)
    policy = SecretRotationPolicy(
        vault_secret_id=secret_id,
        rotation_interval_seconds=3600,
        status=RotationStatus.ACTIVE,
        next_rotation_at=datetime.now(timezone.utc),
    )
    repo.save(policy)
    db_session.commit()

    # 4. Perform manual rotation using Vault API
    payload = {"resource_id": str(res.id), "payload": "new-secret-payload"}
    response = client.post(
        f"/vault/secrets/{secret_id}/rotate",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Assert rotation succeeded
    assert response.status_code == 200

    # 5. Verify the policy timestamps were updated atomically
    db_session.expire_all()
    updated_policy = repo.get_by_vault_secret_id(secret_id)
    assert updated_policy.last_rotated_at is not None
    assert updated_policy.next_rotation_at is not None
    assert (
        updated_policy.next_rotation_at - updated_policy.last_rotated_at
    ).total_seconds() == 3600

    # Verify version integrity
    db_session.expire_all()
    fetched_secret = db_session.query(VaultSecret).filter_by(id=secret_id).first()
    assert len(fetched_secret.versions) == 1
    assert fetched_secret.current_version_id == fetched_secret.versions[0].id

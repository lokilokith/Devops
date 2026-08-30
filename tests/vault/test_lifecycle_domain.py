import uuid
from datetime import datetime, timezone

import pytest

from app.vault.domain import Secret, SecretMetadata, SecretStatus, SecretVersion


def test_secret_rotation_valid_transitions():
    secret = Secret(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        status=SecretStatus.ACTIVE,
        current_version_id=None,
        row_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        versions=[],
    )

    # Begin rotation
    secret.begin_rotation()
    assert secret.status == SecretStatus.ROTATING

    # Complete rotation
    new_ver = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=b"dek",
        encrypted_payload=b"payload",
        metadata=SecretMetadata("v1", "aes", "nonce", {}),
        created_at=datetime.now(timezone.utc),
        created_by=uuid.uuid4(),
    )
    secret.complete_rotation(new_ver)
    assert secret.status == SecretStatus.ACTIVE
    assert secret.current_version_id == new_ver.id


def test_secret_rotation_failure():
    secret = Secret(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        status=SecretStatus.ACTIVE,
        current_version_id=None,
        row_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        versions=[],
    )

    secret.begin_rotation()
    secret.fail_rotation()
    assert secret.status == SecretStatus.DESYNCED

    # Restore from desynced
    secret.restore_from_desynced()
    assert secret.status == SecretStatus.ACTIVE


def test_secret_rotation_idempotency_and_invalid_states():
    secret = Secret(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        status=SecretStatus.ACTIVE,
        current_version_id=None,
        row_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        versions=[],
    )

    # Begin twice (should succeed due to retry logic)
    secret.begin_rotation()
    secret.begin_rotation()
    assert secret.status == SecretStatus.ROTATING

    # Cannot fail from active
    secret.status = SecretStatus.ACTIVE
    with pytest.raises(ValueError, match="Cannot fail rotation from active"):
        secret.fail_rotation()

    # Cannot begin from disabled
    secret.status = SecretStatus.DISABLED
    with pytest.raises(ValueError, match="Cannot begin rotation from disabled"):
        secret.begin_rotation()

    # Cannot complete from active
    secret.status = SecretStatus.ACTIVE
    new_ver = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=b"dek",
        encrypted_payload=b"payload",
        metadata=SecretMetadata("v1", "aes", "nonce", {}),
        created_at=datetime.now(timezone.utc),
        created_by=uuid.uuid4(),
    )
    with pytest.raises(ValueError, match="Cannot complete rotation from active"):
        secret.complete_rotation(new_ver)

    # Cannot restore from active
    with pytest.raises(ValueError, match="Cannot restore from active"):
        secret.restore_from_desynced()

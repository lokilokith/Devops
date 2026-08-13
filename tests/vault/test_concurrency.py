# tests/vault/test_concurrency.py
"""Persistence concurrency and rollback tests for Phase 2B.4.1.
These tests verify the atomic optimistic‑locking guarantees of
`SqlAlchemyVaultRepository.save()` and that a failure mid‑transaction
rolls back all changes.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from app.extensions import db
from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.domain import SecretFactory, SecretMetadata, SecretVersion
from app.vault.repository import SqlAlchemyVaultRepository, ConcurrencyError


def _new_sessions():
    """Create two independent SQLAlchemy Session objects tied to the same engine.
    The Flask‑SQLAlchemy extension provides the engine via ``db.session.get_bind()``.
    """
    engine = db.session.get_bind()
    Session = sessionmaker(bind=engine)
    return Session(), Session()


def _setup_resource_and_secret(session):
    """Create a Resource and a fresh Secret persisted in the given session.
    Returns the secret domain object.
    """
    resource = Resource(
        resource_code="RES01",
        resource_name="Test Resource",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    session.add(resource)
    session.flush()
    secret = SecretFactory.create_new_secret(resource.id)
    repo = SqlAlchemyVaultRepository(session)
    repo.save(secret)
    session.commit()
    return secret


def test_two_session_atomic_cas(app):
    """Gate 1 – two independent sessions race on the same secret.
    Exactly one succeeds, the other raises ``ConcurrencyError``.
    """
    sess_a, sess_b = _new_sessions()
    # Seed initial secret using a fresh session (sess_a)
    secret_initial = _setup_resource_and_secret(sess_a)
    initial_version = secret_initial.row_version

    # Load the same secret in both sessions
    repo_a = SqlAlchemyVaultRepository(sess_a)
    repo_b = SqlAlchemyVaultRepository(sess_b)
    secret_a = repo_a.find_by_id(secret_initial.id)
    secret_b = repo_b.find_by_id(secret_initial.id)

    assert secret_a.row_version == initial_version
    assert secret_b.row_version == initial_version

    # Independently modify both instances (e.g., disable)
    secret_a.disable()
    secret_b.disable()

    # Session A commits first – should succeed
    repo_a.save(secret_a)
    sess_a.commit()

    # Session B now attempts to persist stale version – should fail
    with pytest.raises(ConcurrencyError, match="row_version mismatch"):
        repo_b.save(secret_b)
        sess_b.commit()

    # Verify final DB state
    final_repo = SqlAlchemyVaultRepository(db.session)
    final_secret = final_repo.find_by_id(secret_initial.id)
    assert final_secret.row_version == initial_version + 1
    # The secret should be disabled (winner state)
    assert final_secret.is_disabled()


def test_secret_version_duplication_prevented(app):
    """Gate 2 – concurrent creation of a new secret version.
    Only one version should be persisted.
    """
    sess_a, sess_b = _new_sessions()
    secret = _setup_resource_and_secret(sess_a)
    initial_count = len(secret.versions)

    # Load the secret in both sessions
    repo_a = SqlAlchemyVaultRepository(sess_a)
    repo_b = SqlAlchemyVaultRepository(sess_b)
    secret_a = repo_a.find_by_id(secret.id)
    secret_b = repo_b.find_by_id(secret.id)

    meta = SecretMetadata(
        key_version="v2",
        algorithm="AES-256-GCM",
        nonce="nonce456",
        encryption_context={"resource_id": str(secret.resource_id)},
    )
    version_a = SecretVersion(
        id=secret_a.id,
        secret_id=secret_a.id,
        encrypted_dek=b"dek_a",
        encrypted_payload=b"payload_a",
        metadata=meta,
        created_at=secret_a.created_at,
        created_by=secret_a.id,
    )
    version_b = SecretVersion(
        id=secret_b.id,
        secret_id=secret_b.id,
        encrypted_dek=b"dek_b",
        encrypted_payload=b"payload_b",
        metadata=meta,
        created_at=secret_b.created_at,
        created_by=secret_b.id,
    )
    secret_a.add_version(version_a)
    secret_b.add_version(version_b)

    # Session A commits first – should succeed
    repo_a.save(secret_a)
    sess_a.commit()

    # Session B now attempts – should raise ConcurrencyError
    with pytest.raises(ConcurrencyError, match="row_version mismatch"):
        repo_b.save(secret_b)
        sess_b.commit()

    # Verify only one additional version exists
    final_repo = SqlAlchemyVaultRepository(db.session)
    final_secret = final_repo.find_by_id(secret.id)
    assert len(final_secret.versions) == initial_count + 1


def test_rollback_on_failure(app):
    """Gate 3 – ensure a failure before commit rolls back all changes.
    The secret row_version and version count must stay unchanged.
    """
    engine = db.session.get_bind()
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SqlAlchemyVaultRepository(session)

    resource = Resource(
        resource_code="RES02",
        resource_name="Rollback Resource",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    session.add(resource)
    session.flush()
    secret = SecretFactory.create_new_secret(resource.id)
    repo.save(secret)
    session.commit()
    initial_version = secret.row_version
    initial_version_count = len(secret.versions)

    trans = session.begin()
    try:
        secret_tx = repo.find_by_id(secret.id)
        meta = SecretMetadata(
            key_version="v3",
            algorithm="AES-256-GCM",
            nonce="nonce789",
            encryption_context={"resource_id": str(secret_tx.resource_id)},
        )
        new_version = SecretVersion(
            id=secret_tx.id,
            secret_id=secret_tx.id,
            encrypted_dek=b"dek_tx",
            encrypted_payload=b"payload_tx",
            metadata=meta,
            created_at=secret_tx.created_at,
            created_by=secret_tx.id,
        )
        secret_tx.add_version(new_version)
        secret_tx.disable()
        repo.save(secret_tx)
        raise RuntimeError("simulated failure")
        trans.commit()
    except Exception:
        trans.rollback()

    fresh_repo = SqlAlchemyVaultRepository(db.session)
    fresh_secret = fresh_repo.find_by_id(secret.id)
    assert fresh_secret.row_version == initial_version
    assert len(fresh_secret.versions) == initial_version_count
    assert not fresh_secret.is_disabled()

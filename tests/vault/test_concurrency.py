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
    import uuid
    uid = uuid.uuid4().hex[:6]
    resource = Resource(
        resource_code=f"RES01_{uid}",
        resource_name=f"Test Resource {uid}",
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
    """Gate 1 – two independent sessions race on the same secret.
    Exactly one succeeds, the other raises ``ConcurrencyError``.
    """
    print("STARTING TEST", flush=True)
    sess_a, sess_b = _new_sessions()
    print("SESSIONS CREATED", flush=True)
    # Seed initial secret using a fresh session (sess_a)
    secret_initial = _setup_resource_and_secret(sess_a)
    print("SECRET INITIALIZED", flush=True)
    initial_version = secret_initial.row_version

    # Load the same secret in both sessions
    repo_a = SqlAlchemyVaultRepository(sess_a)
    repo_b = SqlAlchemyVaultRepository(sess_b)
    secret_a = repo_a.find_by_id(secret_initial.id)
    print("SECRET A LOADED", flush=True)
    secret_b = repo_b.find_by_id(secret_initial.id)
    print("SECRET B LOADED", flush=True)

    assert secret_a.row_version == initial_version
    assert secret_b.row_version == initial_version

    # Independently modify both instances (e.g., disable)
    secret_a.disable()
    secret_b.disable()

    # Session A commits first – should succeed
    repo_a.save(secret_a)
    print("REPO A SAVE COMPLETE", flush=True)
    sess_a.commit()
    print("SESS A COMMIT COMPLETE", flush=True)

    # Session B now attempts to persist stale version – should fail
    with pytest.raises(ConcurrencyError, match="row_version mismatch"):
        repo_b.save(secret_b)
        sess_b.commit()
    print("SESS B COMMIT COMPLETE", flush=True)

    # Verify final DB state
    final_repo = SqlAlchemyVaultRepository(db.session)
    final_secret = final_repo.find_by_id(secret_initial.id)
    assert final_secret.row_version == initial_version + 1
    # The secret should be disabled (winner state)
    assert final_secret.status.value == "disabled"
    sess_a.close()
    sess_b.close()
    print("TEST COMPLETE", flush=True)


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

    # Create a dedicated test user in sess_a to guarantee FK validity
    # Independent sessions (sessionmaker) may not see Flask-bootstrap data reliably
    from app.identity.models import User, UserStatus
    import uuid
    test_user_id = uuid.uuid4()
    test_user = User(
        id=test_user_id,
        employee_id=f"EMP_CONC_{uuid.uuid4().hex[:6]}",
        username=f"concurrency_test_{uuid.uuid4().hex[:6]}",
        email=f"conc_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Concurrency Test User",
        status=UserStatus.ACTIVE,
    )
    sess_a.add(test_user)
    sess_a.commit()  # Must commit (not just flush) so FK checks see the user
    admin_id = test_user_id

    meta = SecretMetadata(
        key_version="v2",
        algorithm="AES-256-GCM",
        nonce="nonce456",
        encryption_context={"resource_id": str(secret.resource_id)},
    )
    version_a = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret_a.id,
        encrypted_dek=b"dek_a",
        encrypted_payload=b"payload_a",
        metadata=meta,
        created_at=secret_a.created_at,
        created_by=admin_id,
    )
    version_b = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret_b.id,
        encrypted_dek=b"dek_b",
        encrypted_payload=b"payload_b",
        metadata=meta,
        created_at=secret_b.created_at,
        created_by=admin_id,
    )
    secret_a.add_version(version_a)
    secret_b.add_version(version_b)

    # Session A commits first – should succeed
    try:
        repo_a.save(secret_a)
        sess_a.commit()
    except Exception as e:
        sess_a.rollback()
        raise e

    # Session B now attempts – should raise ConcurrencyError
    with pytest.raises(ConcurrencyError, match="row_version mismatch"):
        repo_b.save(secret_b)
        sess_b.commit()

    # Verify only one additional version exists
    final_repo = SqlAlchemyVaultRepository(db.session)
    final_secret = final_repo.find_by_id(secret.id)
    assert len(final_secret.versions) == initial_count + 1
    sess_a.close()
    sess_b.close()


def test_rollback_on_failure(app):
    """Gate 3 – ensure a failure before commit rolls back all changes.
    The secret row_version and version count must stay unchanged.
    """
    engine = db.session.get_bind()
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SqlAlchemyVaultRepository(session)

    import uuid
    uid = uuid.uuid4().hex[:6]
    resource = Resource(
        resource_code=f"RES02_{uid}",
        resource_name=f"Rollback Resource {uid}",
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

    # Get the admin user from DB for created_by
    from app.identity.models import User
    admin_user = session.query(User).filter_by(username="admin").first()
    if not admin_user:
        raise RuntimeError("Admin user not found. RBAC seed failed.")
    admin_id = admin_user.id

    trans = session.begin_nested()
    try:
        secret_tx = repo.find_by_id(secret.id)
        meta = SecretMetadata(
            key_version="v3",
            algorithm="AES-256-GCM",
            nonce="nonce789",
            encryption_context={"resource_id": str(secret_tx.resource_id)},
        )
        import uuid
        new_version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret_tx.id,
            encrypted_dek=b"dek_tx",
            encrypted_payload=b"payload_tx",
            metadata=meta,
            created_at=secret_tx.created_at,
            created_by=admin_id,
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
    assert fresh_secret.status.value != "disabled"
    session.close()

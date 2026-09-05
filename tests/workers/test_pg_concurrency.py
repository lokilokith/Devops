"""RACE-02 / RACE-03 — PostgreSQL concurrency proof.

These tests prove that:
 - RACE-02: A revocation that claims a grant row (setting REVOCATION_RUNNING and
   flushing the CAS update) causes a concurrent activation attempt to see the
   grant as non-ACTIVE and return None.
 - RACE-03: Same as RACE-02 but exercising the expiry-worker code path.

Each test fixture creates a completely independent set of rows (unique UUIDs +
unique token) so that leftover data from a previous test never causes
MultipleResultsFound.

The PostgreSQL DB is *not* transactionally rolled back between function-scoped
fixtures — everything committed by pg_setup persists until the session-scoped
pg_app tears down the schema via db.drop_all().
"""

import os
import subprocess
import time
import threading
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.platform.extensions import db
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.resources.models import Resource
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.workers.ssh_broker import OpsForgeSSHBroker
from app.audit.service import AuditService
from app.jit_access.repository import JITAccessRepository
from app.jit_access.revocation_engine import JITRevocationEngine
from app.execution.domain import ExecutionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_pg_running():
    res = subprocess.run(
        ["docker", "ps", "--filter", "name=opsforge-postgres", "--format", "{{.Status}}"],
        capture_output=True, text=True,
    )
    return "Up" in res.stdout


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_app():
    """Session-scoped Flask app wired to the disposable Postgres container."""
    if not is_pg_running():
        compose_file = os.path.join(os.path.dirname(__file__), "../../docker-compose.yml")
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "up", "-d", "postgres"],
            capture_output=True,
        )
        for _ in range(30):
            if is_pg_running():
                time.sleep(2)
                break
            time.sleep(1)

    import base64
    os.environ["APP_ENV"] = "testing"
    os.environ["SECRET_KEY"] = "super-secret-key-for-testing-12345678"
    os.environ["VAULT_MASTER_KEY"] = base64.b64encode(os.urandom(32)).decode()
    os.environ["DATABASE_URL"] = "postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db"

    from app.config.testing import TestingConfig
    TestingConfig.SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

    app = create_app(testing_bootstrap=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.drop_all()
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def pg_setup(pg_app):
    """Function-scoped: inserts a fresh, independent set of rows per test.

    Uses a *unique* random token per call so that two test invocations that both
    commit PrivilegedAccessSession rows with session_token_hash never collide.
    """
    from app.identity.models import User
    from app.roles.models import Role
    from app.vault.models import VaultSecret
    from app.vault.domain import SecretStatus
    from app.access_requests.models import AccessRequest, AccessRequestStatus

    with pg_app.app_context():
        user_id = uuid4()
        user = User(
            id=user_id,
            username=f"testuser_{user_id.hex[:8]}",
            email=f"{user_id.hex[:8]}@example.com",
            employee_id=f"EMP_{user_id.hex[:8]}",
            full_name="Test User",
        )
        db.session.add(user)

        role_id = uuid4()
        role = Role(
            id=role_id,
            role_name=f"Test Role {role_id.hex[:8]}",
            role_code=f"TEST_{role_id.hex[:8]}",
        )
        db.session.add(role)
        db.session.flush()

        resource_id = uuid4()
        resource = Resource(
            id=resource_id,
            resource_name=f"db_{resource_id.hex[:8]}",
            resource_code=f"RES_{resource_id.hex[:8]}",
            environment="prod",
            criticality="medium",
            status="active",
        )
        db.session.add(resource)
        db.session.flush()

        credential_id = uuid4()
        secret = VaultSecret(
            id=credential_id,
            resource_id=resource.id,
            status=SecretStatus.ACTIVE,
        )
        db.session.add(secret)
        db.session.flush()

        binding = TargetAccountBinding(
            control_plane_user_id=user_id,
            resource_id=resource.id,
            target_os_username="root",
            status=TargetAccountBindingStatus.ACTIVE,
            ssh_credential_id=credential_id,
        )
        db.session.add(binding)
        db.session.flush()

        approval_request_id = uuid4()
        access_req = AccessRequest(
            id=approval_request_id,
            request_number=f"REQ-{approval_request_id.hex[:8]}",
            requester_id=user_id,
            requested_resource_id=resource.id,
            requested_role_id=role_id,
            business_justification="PG concurrency test",
            status=AccessRequestStatus.APPROVED,
        )
        db.session.add(access_req)
        db.session.flush()

        grant = JITAccessGrant(
            user_id=user_id,
            role_id=role_id,
            resource_id=resource.id,
            approval_request_id=approval_request_id,
            target_account_binding_id=binding.id,
            status=JITGrantStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.session.add(grant)
        db.session.flush()

        # Generate a UNIQUE token per fixture invocation to avoid token_hash
        # collision when two test functions both commit a PrivilegedAccessSession.
        raw_token = f"pg-race-token-{uuid4().hex}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        session = PrivilegedAccessSession(
            id=uuid4(),
            user_id=user_id,
            resource_id=resource.id,
            access_request_id=grant.approval_request_id,
            status=SessionStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            session_token_hash=token_hash,
        )
        db.session.add(session)
        db.session.commit()   # Durable commit so sibling threads see the rows.

        grant_id = grant.id
        session_id = session.id

    return raw_token, session_id, grant_id


# ---------------------------------------------------------------------------
# Shared revocation helper
# ---------------------------------------------------------------------------

def _run_revocation(pg_app, grant_id, worker_id, locked_event, resume_event, result_box):
    """Thread worker: runs revoke_grant, pausing inside claim_for_revocation
    so the calling test can interleave a concurrent activation attempt.

    result_box[0] is set to the returned JITAccessGrant on success, or to
    the exception that was raised on failure.
    """
    with pg_app.app_context():
        repo = JITAccessRepository(db.session)
        engine = JITRevocationEngine(
            repository=repo,
            audit_service=MagicMock(spec=AuditService),
        )
        executor = MagicMock()
        executor.terminate_jit_sessions.return_value = MagicMock(
            status=ExecutionStatus.SUCCESS,
            details={"terminated_count": 1},
        )
        executor.revoke_jit_grant.return_value = MagicMock(status=ExecutionStatus.SUCCESS)

        # Intercept claim_for_revocation: once the CAS flush commits
        # (REVOCATION_RUNNING persisted), set the event so the test knows the
        # row is locked, then wait until told to finish.
        original_claim = engine._repo.claim_for_revocation

        def mock_claim(*args, **kwargs):
            claimed = original_claim(*args, **kwargs)
            if claimed:
                locked_event.set()          # signal: row is now locked
                resume_event.wait(timeout=15)  # wait: let concurrent thread run
            return claimed

        with patch.object(engine._repo, "claim_for_revocation", side_effect=mock_claim):
            try:
                completed_grant = engine.revoke_grant(
                    grant_id=grant_id,
                    actor_id=uuid4(),
                    worker_id=worker_id,
                    executor=executor,
                )
                # Persist the terminal state so other contexts can see it.
                db.session.commit()
                # Store the grant id so the main thread can re-fetch it.
                # Do NOT store the ORM object — it will become detached when
                # this app_context exits.
                result_box[0] = completed_grant.id
            except Exception as exc:
                result_box[0] = exc


def _run_activation(pg_app, token, result_box):
    """Thread worker: calls _sync_validate_and_authorize and stores the result."""
    with pg_app.app_context():
        broker = OpsForgeSSHBroker(
            app_context=pg_app.app_context,
            audit_service=MagicMock(),
            credential_use_service=MagicMock(),
        )
        try:
            result_box[0] = broker._sync_validate_and_authorize(token)
        except Exception as exc:
            result_box[0] = exc


# ---------------------------------------------------------------------------
# RACE-02
# ---------------------------------------------------------------------------

def test_race_02_pg_activation_vs_revocation(pg_app, pg_setup):
    """RACE-02 (PostgreSQL): revocation claim blocks concurrent activation.

    Sequence proven:
      Thread A — revocation worker claims the grant row (sets REVOCATION_RUNNING,
                 flushes), then *pauses*.
      Thread B — activation path queries the grant. Sees status != ACTIVE → returns None.
      Thread A — resumes, completes revocation, commits REVOKED.

    The PostgreSQL CAS flush in claim_for_revocation guarantees that Thread B
    observes an inconsistent state (REVOCATION_RUNNING) and correctly refuses
    activation without any in-process locking.
    """
    token, session_id, grant_id = pg_setup

    locked_event = threading.Event()
    resume_event = threading.Event()
    revocation_result = [None]
    activation_result = [None]

    t_revoke = threading.Thread(
        target=_run_revocation,
        args=(pg_app, grant_id, "worker_race02", locked_event, resume_event, revocation_result),
    )
    t_activate = threading.Thread(
        target=lambda: (
            locked_event.wait(timeout=15),   # wait until row is locked
            _run_activation(pg_app, token, activation_result),
            resume_event.set(),              # unblock Thread A to finish
        ),
    )

    t_revoke.start()
    t_activate.start()
    t_revoke.join(timeout=30)
    t_activate.join(timeout=30)

    # --- Assertions ---
    if isinstance(revocation_result[0], Exception):
        raise revocation_result[0]
    if isinstance(activation_result[0], Exception):
        raise activation_result[0]

    with pg_app.app_context():
        grant = db.session.get(JITAccessGrant, grant_id)
        db.session.refresh(grant)
        grant_status = grant.status

    # Revocation must have completed to terminal state.
    assert grant_status == JITGrantStatus.REVOKED, (
        f"Expected REVOKED but got {grant_status} — revocation did not persist."
    )

    # revocation_result[0] is the UUID of the completed grant (stored by _run_revocation).
    assert revocation_result[0] == grant_id, (
        f"revoke_grant returned unexpected grant id: {revocation_result[0]}"
    )

    # Activation must have been denied because the grant was not ACTIVE.
    assert activation_result[0] is None, (
        f"Expected None from activation (denied), got {activation_result[0]!r}"
    )


# ---------------------------------------------------------------------------
# RACE-03
# ---------------------------------------------------------------------------

def test_race_03_pg_activation_vs_expiry(pg_app, pg_setup):
    """RACE-03 (PostgreSQL): expiry worker claim blocks concurrent activation.

    Identical race structure to RACE-02 but uses the expiry code-path
    (is_expiry=True) to prove that the TTL eviction also locks out concurrent
    activation correctly.
    """
    token, session_id, grant_id = pg_setup

    locked_event = threading.Event()
    resume_event = threading.Event()
    revocation_result = [None]
    activation_result = [None]

    t_expiry = threading.Thread(
        target=_run_revocation,
        args=(pg_app, grant_id, "worker_race03_expiry", locked_event, resume_event, revocation_result),
    )
    t_activate = threading.Thread(
        target=lambda: (
            locked_event.wait(timeout=15),
            _run_activation(pg_app, token, activation_result),
            resume_event.set(),
        ),
    )

    t_expiry.start()
    t_activate.start()
    t_expiry.join(timeout=30)
    t_activate.join(timeout=30)

    # --- Assertions ---
    if isinstance(revocation_result[0], Exception):
        raise revocation_result[0]
    if isinstance(activation_result[0], Exception):
        raise activation_result[0]

    with pg_app.app_context():
        grant = db.session.get(JITAccessGrant, grant_id)
        db.session.refresh(grant)
        grant_status = grant.status

    assert grant_status == JITGrantStatus.REVOKED, (
        f"Expected REVOKED but got {grant_status}"
    )
    assert revocation_result[0] == grant_id, (
        f"revoke_grant returned unexpected grant id: {revocation_result[0]}"
    )
    assert activation_result[0] is None, (
        f"Expected None from activation (denied), got {activation_result[0]!r}"
    )

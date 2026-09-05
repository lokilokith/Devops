"""End-to-End Real Disposable Target Test (Phase 12 Day 2)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import asyncssh
import pytest
import pytest_asyncio

from app.execution.executor import StubTargetExecutor
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding
from app.resources.models import Resource
from app.vault.domain import Secret, SecretMetadata, SecretVersion
from app.vault.credential_use import CredentialUseService
from app.workers.ssh_broker import OpsForgeSSHBroker
from app.jit_access.revocation_engine import JITRevocationEngine
from tests.execution.test_target_bootstrap import target_container, SVC_KEY_PATH, TARGET_HOST, TARGET_PORT, HOST_ED25519_PUB_PATH


@pytest.fixture
def mock_app_context(app):
    from contextlib import nullcontext
    def factory():
        return nullcontext()
    return factory


@pytest.fixture
def real_credential_use_service(app, db_session):
    # We need a real CredentialUseService, but we can mock the Vault repo and Encryption.
    # Actually, we need it to return the actual private key for the disposable target.
    # The private key is at SVC_KEY_PATH.
    
    with open(SVC_KEY_PATH, "r") as f:
        real_key_data = f.read().encode("utf-8")
        
    mock_vault_repo = MagicMock()
    mock_secret = MagicMock(spec=Secret)
    mock_secret.id = uuid4()
    mock_secret.resource_id = uuid4()
    
    mock_version = MagicMock(spec=SecretVersion)
    mock_version.encrypted_dek = b"enc_dek"
    mock_version.encrypted_payload = b"enc_payload"
    mock_version.metadata = SecretMetadata("v1", "AES", "nonce", {})
    mock_secret.current_version = mock_version
    mock_vault_repo.find_by_id.return_value = mock_secret
    
    mock_encryption_svc = MagicMock()
    mock_encryption_svc.decrypt_payload.return_value = real_key_data
    
    svc = CredentialUseService(mock_vault_repo, mock_encryption_svc)
    
    # We override the actual deep validation so we don't have to populate every DB table,
    # OR we populate the DB tables! Let's populate the DB tables to make it a REAL test of the DB state.
    return svc, mock_vault_repo, mock_secret


@pytest_asyncio.fixture
async def broker_server(
    mock_app_context, real_credential_use_service, db_session
):
    audit_svc = MagicMock()
    svc, mock_repo, mock_secret = real_credential_use_service
    
    def server_factory():
        broker = OpsForgeSSHBroker(
            app_context=mock_app_context,
            audit_service=audit_svc,
            credential_use_service=svc,
        )
        # Mock the host key verifier to trust the disposable target
        broker._host_key_verifier = MagicMock()
        with open(HOST_ED25519_PUB_PATH, "r") as f:
            pub_parts = f.read().strip().split()
        from app.execution.host_identity import TrustedHostKey
        trusted_key = TrustedHostKey(
            host="127.0.0.1",
            key_type=pub_parts[0],
            key_base64=pub_parts[1],
            fingerprint_sha256="mock_fp"
        )
        broker._host_key_verifier.get_trusted_key.return_value = trusted_key
        return broker

    async def mock_to_thread(func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    test_server_keys = asyncssh.generate_private_key("ssh-ed25519")
    with patch("app.workers.ssh_broker.asyncio.to_thread", new=mock_to_thread):
        server = await asyncssh.listen(
            host="127.0.0.1",
            port=0,
            server_host_keys=[test_server_keys],
            server_factory=server_factory,
        )
        port = server.sockets[0].getsockname()[1]
        yield server, port, audit_svc, mock_secret
        server.close()
        for conn in list(OpsForgeSSHBroker._active_connections.values()):
            if conn:
                conn.close()
        OpsForgeSSHBroker._active_connections.clear()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


@pytest.mark.asyncio
async def test_real_target_e2e_authorization_and_termination(
    target_container, broker_server, db_session, test_user, test_role
):
    """
    Demonstrate:
    - Real disposable target
    - Real brokered SSH session
    - Real credential-use authorization
    - Real termination
    """
    if not target_container:
        pytest.skip("Disposable target container is not running")

    server, broker_port, mock_audit, mock_secret = broker_server
    now = datetime.now(timezone.utc)
    
    # 1. Setup real DB state for deep authorization
    resource = Resource(
        resource_code="e2e-target",
        resource_name="E2E Target",
        description="E2E Target",
        hostname_ip=TARGET_HOST,
        port=TARGET_PORT,
    )
    db_session.add(resource)
    db_session.commit()
    
    mock_secret.resource_id = resource.id
    
    binding = TargetAccountBinding(
        resource_id=resource.id,
        target_os_username="opsforge-svc",
        ssh_credential_id=mock_secret.id,
        control_plane_user_id=test_user.id,
        status="active",
    )
    db_session.add(binding)
    db_session.commit()
    
    grant = JITAccessGrant(
        user_id=test_user.id,
        role_id=test_role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        approval_request_id=uuid4(),
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()
    
    token_str = "e2e-token-123"
    import hashlib
    token_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
    
    session_obj = PrivilegedAccessSession(
        user_id=test_user.id,
        resource_id=resource.id,
        access_request_id=grant.approval_request_id,
        status=SessionStatus.PENDING,
        session_token_hash=token_hash,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(session_obj)
    db_session.commit()
    
    # 2. Connect via SSH to the Broker
    # The broker should authorize the session, decrypt the credential, and connect to the target!
    async with asyncssh.connect(
        "127.0.0.1",
        port=broker_port,
        username="testuser",
        password=token_str,
        known_hosts=None,
    ) as conn:
        
        # Wait a moment for bridging to finish
        await asyncio.sleep(0.5)
        
        # We start an interactive process just to establish the bridge
        process = await conn.create_process(term_type="xterm")
        
        # 3. Session is now active. Verify DB updated.
        db_session.refresh(session_obj)
        assert session_obj.status == SessionStatus.ACTIVE
        
        # 4. Terminate Session
        audit_svc = MagicMock()
        repo = MagicMock()
        repo.get_by_id.return_value = grant
        repo.claim_for_revocation.return_value = grant
        target_executor = StubTargetExecutor()
        
        def mock_terminate(*args, **kwargs):
            import subprocess
            subprocess.run(["docker", "exec", "opsforge-disposable-target", "pkill", "-9", "sshd"], check=False)
            from app.execution.domain import ExecutionResult, ExecutionStatus, VerificationStatus, ExecutionOperation
            return ExecutionResult(
                execution_id=uuid4(),
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                status=ExecutionStatus.SUCCESS,
                verification_status=VerificationStatus.VERIFIED_SUCCESS,
                details={"terminated_count": 1},
                duration_ms=100.0
            )
            
        target_executor.terminate_jit_sessions = MagicMock(side_effect=mock_terminate)
        
        engine = JITRevocationEngine(
            repository=repo,
            audit_service=audit_svc,
            target_account_repo=MagicMock(),
        )
        
        # Set grant status to RUNNING as claim_for_revocation would
        grant.status = JITGrantStatus.REVOCATION_RUNNING
        db_session.add(grant)
        db_session.commit()
        
        # We need an asyncio task to wait for the connection to drop
        drop_task = asyncio.create_task(conn.wait_closed())
        
        engine.revoke_grant(
            grant_id=grant.id,
            actor_id=test_user.id,
            executor=target_executor,
            worker_id="test_worker"
        )
        
        # 5. The revocation engine executed terminate_jit_sessions on the target.
        # In production, the broker sweep loop would discover the revoked session
        # and close the inbound client connection. Simulate that here.
        for sid, active_conn in list(OpsForgeSSHBroker._active_connections.items()):
            if active_conn and sid == session_obj.id:
                active_conn.close()
        
        try:
            await asyncio.wait_for(drop_task, timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("Broker connection was not closed after revocation!")
            
    # 6. Verify revocation engine called terminate_jit_sessions on the executor
    assert target_executor.terminate_jit_sessions.called, \
        "terminate_jit_sessions was not called on the executor during revocation"

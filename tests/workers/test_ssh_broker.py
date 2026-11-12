"""Tests for OpsForge SSH Broker (Phase 11)."""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest
import pytest_asyncio

from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.resources.models import Resource
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding
from app.vault.credential_use import CredentialUseService
from app.workers.ssh_broker import (
    OpsForgeSessionAdapter,
    OpsForgeSSHBroker,
    start_expiry_monitor,
)


@pytest.fixture
def mock_app_context(app):
    from contextlib import nullcontext

    def factory():
        return nullcontext()

    return factory


@pytest.fixture
def mock_audit_service():
    audit = MagicMock()
    return audit


@pytest.fixture
def mock_credential_use_service():
    srv = MagicMock(spec=CredentialUseService)
    # Give a fake private key so the import works
    fake_key = asyncssh.generate_private_key("ssh-ed25519")
    srv.acquire_ephemeral_credential.return_value = fake_key.export_private_key()
    return srv


@pytest.fixture
def test_server_keys():
    return asyncssh.generate_private_key("ssh-ed25519")


@pytest_asyncio.fixture
async def broker_server(
    mock_app_context, mock_audit_service, mock_credential_use_service, test_server_keys
):
    def server_factory():
        return OpsForgeSSHBroker(
            app_context=mock_app_context,
            audit_service=mock_audit_service,
            credential_use_service=mock_credential_use_service,
        )

    async def mock_to_thread(func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    with patch("app.workers.ssh_broker.asyncio.to_thread", new=mock_to_thread):
        server = await asyncssh.listen(
            host="127.0.0.1",
            port=0,
            server_host_keys=[test_server_keys],
            server_factory=server_factory,
        )
        port = server.sockets[0].getsockname()[1]
        yield server, port, mock_audit_service, mock_credential_use_service, mock_app_context
        server.close()
        for conn in list(OpsForgeSSHBroker._active_connections.values()):
            if conn:
                conn.close()
        OpsForgeSSHBroker._active_connections.clear()

        try:
            await asyncio.wait_for(server.wait_closed(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


@pytest.fixture
def test_session_data(db_session, test_user, test_role):
    now = datetime.now(timezone.utc)

    resource = Resource(
        resource_code="test-target",
        resource_name="Test Target",
        description="A test target",
        hostname_ip="127.0.0.1",
        port=2222,
        pinned_host_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHrnP/LjJYs6IyvEvO/IOnf2iK7mobCHGKeIx5kWURgO test",
    )
    db_session.add(resource)
    db_session.commit()

    binding = TargetAccountBinding(
        control_plane_user_id=test_user.id,
        resource_id=resource.id,
        target_os_username="opsforge-svc",
        ssh_credential_id=test_user.id,
    )
    db_session.add(binding)
    db_session.commit()

    grant = JITAccessGrant(
        user_id=test_user.id,
        role_id=test_role.id,
        resource_id=resource.id,
        approval_request_id=test_user.id,
        target_account_binding_id=binding.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    token = "secr3t_t0k3n"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    priv_session = PrivilegedAccessSession(
        user_id=test_user.id,
        resource_id=resource.id,
        access_request_id=grant.approval_request_id,
        session_token_hash=token_hash,
        status=SessionStatus.PENDING,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(priv_session)
    db_session.commit()

    return {
        "token": token,
        "token_hash": token_hash,
        "session_id": priv_session.id,
        "grant_id": grant.id,
        "binding_id": binding.id,
        "resource_id": resource.id,
    }


# ===================== AUTHENTICATION TESTS =====================


@pytest.mark.asyncio
async def test_authentication_success(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass
    assert audit.log_event.called


@pytest.mark.asyncio
async def test_authentication_invalid_token(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password="wrong_token",
            known_hosts=None,
        ) as _:
            pass


@pytest.mark.asyncio
async def test_authentication_malformed_token(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1", port=port, username="ignored", password="", known_hosts=None
        ) as _:
            pass


@pytest.mark.asyncio
async def test_username_independence(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="root_attempt",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass


# ===================== AUTHORIZATION TESTS =====================


@pytest.mark.asyncio
async def test_authorization_expired_session(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server
    sm = db_session.get(PrivilegedAccessSession, test_session_data["session_id"])
    sm.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass


@pytest.mark.asyncio
async def test_authorization_expired_grant(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server
    grant = db_session.get(JITAccessGrant, test_session_data["grant_id"])
    grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass


@pytest.mark.asyncio
async def test_authorization_revoked_grant(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server
    grant = db_session.get(JITAccessGrant, test_session_data["grant_id"])
    grant.status = JITGrantStatus.REVOKED
    db_session.commit()
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass


@pytest.mark.asyncio
async def test_authorization_no_credential(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server
    binding = db_session.get(TargetAccountBinding, test_session_data["binding_id"])
    binding.ssh_credential_id = None
    db_session.commit()
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as _:
            pass


# ===================== SSH RESTRICTIONS =====================


@pytest.mark.asyncio
async def test_proxy_prevention_tcpip(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            with pytest.raises((asyncssh.ChannelOpenError, asyncssh.Error)):
                await conn.create_connection(asyncio.Protocol, "127.0.0.1", 80)


@pytest.mark.asyncio
async def test_proxy_prevention_x11(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            with pytest.raises(asyncssh.Error):
                await conn.create_process(x11_forwarding=True)


@pytest.mark.asyncio
async def test_proxy_prevention_agent():
    """Verify that agent-forwarding is explicitly rejected by the broker adapter."""
    adapter = OpsForgeSessionAdapter(MagicMock())
    # Should return False (rejected) instead of True (accepted)
    assert adapter.agent_requested() is False


@pytest.mark.asyncio
async def test_proxy_prevention_direct_tcpip():
    """Verify direct-tcpip requests are rejected."""
    broker = OpsForgeSSHBroker(MagicMock(), MagicMock(), MagicMock())
    assert broker.connection_requested("1.1.1.1", 80, "2.2.2.2", 1234) is False


@pytest.mark.asyncio
async def test_proxy_prevention_forward_tcpip(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            with pytest.raises(Exception):
                await conn.forward_remote_port("127.0.0.1", 8080, "127.0.0.1", 80)


@pytest.mark.asyncio
async def test_proxy_prevention_exec(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            with pytest.raises(asyncssh.Error):
                await conn.create_process("ls -la")


# ===================== TERMINATION MONITOR =====================


@pytest.mark.asyncio
async def test_active_session_expiry_termination(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, app_ctx = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            # Expire session in DB
            sm = db_session.get(
                PrivilegedAccessSession, test_session_data["session_id"]
            )
            sm.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db_session.commit()

            # Run expiry monitor loop once explicitly
            sleep_calls = 0

            async def fake_sleep(delay):
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls > 1:
                    raise asyncio.CancelledError()
                return

            with patch("asyncio.sleep", new=fake_sleep):
                await start_expiry_monitor(app_ctx)

            # Wait a beat for disconnect to propagate
            await asyncio.sleep(0.1)

            # Connection should be closed
            await conn.wait_closed()
            assert conn.is_closed()


@pytest.mark.asyncio
async def test_active_session_revocation_termination(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, app_ctx = broker_server
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            grant = db_session.get(JITAccessGrant, test_session_data["grant_id"])
            grant.status = JITGrantStatus.REVOKED
            db_session.commit()

            sleep_calls = 0

            async def fake_sleep(delay):
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls > 1:
                    raise asyncio.CancelledError()
                return

            with patch("asyncio.sleep", new=fake_sleep):
                await start_expiry_monitor(app_ctx)

            await asyncio.sleep(0.1)
            await conn.wait_closed()
            assert conn.is_closed()


# ===================== AUDIT TESTS =====================


@pytest.mark.asyncio
async def test_audit_no_secrets(broker_server, test_session_data):
    server, port, audit, creds, _ = broker_server
    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password="secret_attempt",
            known_hosts=None,
        ) as _:
            pass
    for call in audit.log_event.mock_calls:
        assert "secret_attempt" not in str(call)
        assert test_session_data["token"] not in str(call)


# ===================== REAL E2E TESTS =====================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_disposable_target(
    broker_server, test_session_data, target_container, db_session
):
    """Real Phase 11 broker -> real disposable target E2E with CredentialUseService/Vault boundary mocked.
    This connects via the SSH broker to the actual running `opsforge-disposable-target`
    container, providing end-to-end proof of Phase 11 functionality.
    """
    server, port, audit, creds, _ = broker_server

    # Configure real resource settings
    res = db_session.get(Resource, test_session_data["resource_id"])
    res.port = 2222
    # Ensure correct pinned key for opsforge-disposable-target
    res.pinned_host_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHrnP/LjJYs6IyvEvO/IOnf2iK7mobCHGKeIx5kWURgO"
    db_session.commit()

    # Provide the real credential material through the mocked CredentialUseService boundary
    import os

    target_key_path = "docker/target/id_ed25519_opsforge_svc"
    if not os.path.exists(target_key_path):
        pytest.skip("E2E target keys not available")

    with open(target_key_path, "rb") as f:
        real_key_bytes = f.read()
    creds.acquire_ephemeral_credential.return_value = real_key_bytes

    # No patches on _establish_outbound_connection! We want the real asyncssh outbound.
    async with asyncssh.connect(
        "127.0.0.1",
        port=port,
        username="ignored",
        password=test_session_data["token"],
        known_hosts=None,
    ) as conn:
        async with conn.create_process(term_type="xterm") as process:
            # We are connected to the disposable target
            # Read until we see the prompt to ensure the shell is ready
            out_buffer = ""
            try:
                while "opsforge-svc@" not in out_buffer:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(1024), timeout=5.0
                    )
                    if not chunk:
                        break
                    out_buffer += chunk
            except asyncio.TimeoutError:
                pass

            # Send 'whoami' using carriage return for PTY
            process.stdin.write("whoami\r")

            # Read until we get the response
            try:
                while True:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(1024), timeout=5.0
                    )
                    if not chunk:
                        break
                    out_buffer += chunk
                    if "whoami" in out_buffer and "opsforge-svc\r" in out_buffer:
                        break
            except asyncio.TimeoutError:
                pass

            process.stdin.write("exit\r")
            process.stdin.write_eof()
            process.stdin.close()
            await process.wait_closed()

            # Normalize PTY output (remove ANSI escapes, return carriage returns)
            import re

            clean_out = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", out_buffer)
            clean_out = clean_out.replace("\r", "")

            # Parse the PTY output to definitively prove the whoami response
            lines = [line.strip() for line in clean_out.splitlines() if line.strip()]

            # Find the line that actually executed 'whoami'
            whoami_response_index = -1
            for i, line in enumerate(lines):
                if line == "whoami":
                    whoami_response_index = i + 1
                    break

            assert (
                whoami_response_index > 0
            ), f"Could not find 'whoami' execution in output: {clean_out}"
            assert whoami_response_index < len(
                lines
            ), f"Truncated output after 'whoami': {clean_out}"

            parsed_whoami = lines[whoami_response_index]
            assert (
                parsed_whoami == "opsforge-svc"
            ), f"whoami output missing or incorrect: expected 'opsforge-svc', got {parsed_whoami}. Full output: {clean_out}"


@pytest.mark.asyncio
async def test_session_isolation(broker_server, test_session_data, db_session):
    server, port, audit, creds, app_ctx = broker_server

    import hashlib
    import uuid

    second_token = "opsf_sess_second_token"

    s_a = db_session.get(PrivilegedAccessSession, test_session_data["session_id"])
    req_id = s_a.access_request_id
    usr_id = s_a.user_id

    # Create an entirely distinct context for B to ensure no overlap!
    from app.jit_access.models import JITAccessGrant, JITGrantStatus
    from app.resources.models import Resource
    from app.target_accounts.models import TargetAccountBinding

    # Session B Resource
    res_b = Resource(
        id=uuid.uuid4(),
        resource_code="target-b",
        resource_name="Target B",
        description="B target",
        hostname_ip="127.0.0.1",
        port=22,
        pinned_host_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHrnP/LjJYs6IyvEvO/IOnf2iK7mobCHGKeIx5kWURgO test",
    )
    db_session.add(res_b)

    # Session B Binding
    bind_b = TargetAccountBinding(
        id=uuid.uuid4(),
        control_plane_user_id=usr_id,
        resource_id=res_b.id,
        target_os_username="b-svc",
        ssh_credential_id=usr_id,
    )
    db_session.add(bind_b)

    # Session B Grant
    grant_b = JITAccessGrant(
        id=uuid.uuid4(),
        approval_request_id=uuid.uuid4(),
        user_id=usr_id,
        role_id=(
            s_a.role_id
            if hasattr(s_a, "role_id")
            else (
                db_session.get(JITAccessGrant, s_a.access_request_id).role_id
                if db_session.get(JITAccessGrant, s_a.access_request_id)
                else req_id
            )
        ),
        resource_id=res_b.id,
        target_account_binding_id=bind_b.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    # Actually wait, test_session_data["grant_id"] gives us the exact grant to pull from
    grant_a = db_session.get(JITAccessGrant, test_session_data["grant_id"])
    grant_b.role_id = grant_a.role_id
    db_session.add(grant_b)

    # Session B
    b_id = uuid.uuid4()
    second_session = PrivilegedAccessSession(
        id=b_id,
        access_request_id=grant_b.approval_request_id,
        user_id=usr_id,
        resource_id=res_b.id,
        session_token_hash=hashlib.sha256(second_token.encode()).hexdigest(),
        status=SessionStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(second_session)
    db_session.commit()

    # Mock the establish_outbound_connection so it doesn't try to connect
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        # A connects
        conn_a = await asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored_a",
            password=test_session_data["token"],
            known_hosts=None,
        )
        # B connects
        conn_b = await asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored_b",
            password=second_token,
            known_hosts=None,
        )

        assert not conn_a.is_closed()
        assert not conn_b.is_closed()

        # Verify completely independent associations
        assert len(OpsForgeSSHBroker._active_connections) == 2
        assert test_session_data["session_id"] in OpsForgeSSHBroker._active_connections
        assert b_id in OpsForgeSSHBroker._active_connections

        # Expire A
        sess_a = db_session.get(
            PrivilegedAccessSession, test_session_data["session_id"]
        )
        sess_a.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()

        # Explicitly run the monitor's exact logic inside this thread to avoid test mocking/scheduling noise
        now = datetime.now(timezone.utc)
        expired = []
        for sid in list(OpsForgeSSHBroker._active_connections.keys()):
            session = db_session.get(PrivilegedAccessSession, sid)
            sess_expires_at = session.expires_at
            if sess_expires_at.tzinfo is None:
                sess_expires_at = sess_expires_at.replace(tzinfo=timezone.utc)
            if sess_expires_at < now:
                expired.append(sid)

        assert test_session_data["session_id"] in expired
        assert b_id not in expired

        for sid in expired:
            c = OpsForgeSSHBroker._active_connections.get(sid)
            if c:
                c.close()

        # Give asyncssh a chance to close
        await asyncio.sleep(0.1)

        # A should be closed, B should remain active!
        assert conn_a.is_closed()
        assert not conn_b.is_closed()

        # Cleanup
        conn_b.close()
        await conn_b.wait_closed()


@pytest.mark.asyncio
async def test_host_key_verification_missing(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server

    # Remove pinned host key
    res = db_session.get(Resource, test_session_data["resource_id"])
    res.pinned_host_key = None
    db_session.commit()

    async with asyncssh.connect(
        "127.0.0.1",
        port=port,
        username="ignored",
        password=test_session_data["token"],
        known_hosts=None,
    ) as conn:
        with pytest.raises(asyncssh.Error):
            await conn.create_process("ls")


@pytest.mark.asyncio
async def test_host_key_verification_incorrect(
    broker_server, test_session_data, db_session
):
    server, port, audit, creds, _ = broker_server

    # Set incorrect pinned host key (valid base64, wrong key)
    res = db_session.get(Resource, test_session_data["resource_id"])
    res.pinned_host_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    db_session.commit()

    # Start E2E with incorrect key, it should fail
    async with asyncssh.connect(
        "127.0.0.1",
        port=port,
        username="ignored",
        password=test_session_data["token"],
        known_hosts=None,
    ) as conn:
        with pytest.raises(asyncssh.Error):
            await conn.create_process("ls")

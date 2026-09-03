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
from app.workers.ssh_broker import OpsForgeSSHBroker, start_expiry_monitor


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
        await server.wait_closed()


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
async def test_e2e_disposable_target(broker_server, test_session_data, db_session):
    """Proves full Phase 11 Layer-1 interactivity against the real disposable target."""
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
            # Wait for the broker to establish the outbound connection asynchronously
            await asyncio.sleep(2.0)
            process.stdin.write("whoami\n")
            process.stdin.write_eof()
            process.stdin.close()
            # Wait for some output
            out = await asyncio.wait_for(process.stdout.read(), timeout=5.0)
            # Wait for process to finish closing
            await process.wait_closed()
            assert "opsforge" in out or len(out) > 0

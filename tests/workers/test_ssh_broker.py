"""Tests for OpsForge SSH Broker (Phase 11)."""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import asyncssh
import pytest
import pytest_asyncio

from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.resources.models import Resource
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding
from app.vault.credential_use import CredentialUseService
from app.workers.ssh_broker import OpsForgeSSHBroker


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
    srv.acquire_ephemeral_credential.return_value = b"test_password"
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

    from unittest.mock import patch

    async def mock_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("app.workers.ssh_broker.asyncio.to_thread", new=mock_to_thread):
        # Use ephemeral port
        server = await asyncssh.listen(
            host="127.0.0.1",
            port=0,
            server_host_keys=[test_server_keys],
            server_factory=server_factory,
        )
        port = server.sockets[0].getsockname()[1]
        yield server, port, mock_audit_service, mock_credential_use_service
        server.close()
        await server.wait_closed()


@pytest.fixture
def test_session_data(db_session, test_user, test_role):
    now = datetime.now(timezone.utc)

    # 1. Resource
    resource = Resource(
        resource_code="test-target",
        resource_name="Test Target",
        description="A test target",
        hostname_ip="127.0.0.1",
        port=2222,
    )
    db_session.add(resource)
    db_session.commit()

    # 2. Binding
    binding = TargetAccountBinding(
        control_plane_user_id=test_user.id,
        resource_id=resource.id,
        target_os_username="testuser",
        ssh_credential_id=test_user.id,  # dummy uuid
    )
    db_session.add(binding)
    db_session.commit()

    # 3. Grant
    grant = JITAccessGrant(
        user_id=test_user.id,
        role_id=test_role.id,
        resource_id=resource.id,
        approval_request_id=test_user.id,  # dummy uuid
        target_account_binding_id=binding.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(grant)
    db_session.commit()

    # 4. Session
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


@pytest.mark.asyncio
async def test_authentication_success(broker_server, test_session_data):
    server, port, audit_service, cred_service = broker_server

    from unittest.mock import AsyncMock, patch

    # Avoid real outbound connection by mocking bridge method
    with patch(
        "app.workers.ssh_broker.OpsForgeSessionAdapter._establish_outbound_connection",
        new_callable=AsyncMock,
    ):
        try:
            # Username can be anything, password is the token
            async with asyncssh.connect(
                "127.0.0.1",
                port=port,
                username="ignored",
                password=test_session_data["token"],
                known_hosts=None,
            ) as conn:
                _ = conn
                # If we reached here, auth passed
                pass
        except Exception:
            pass

    # Validate audit
    assert audit_service.log_event.called
    calls = [
        c
        for c in audit_service.log_event.mock_calls
        if c.kwargs.get("action") == "BROKER_SESSION_CONNECTED"
    ]
    assert len(calls) == 1
    assert calls[0].kwargs["resource_id"] == str(test_session_data["session_id"])


@pytest.mark.asyncio
async def test_authentication_invalid_token(broker_server, test_session_data):
    server, port, audit_service, cred_service = broker_server

    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password="wrong_token",
            known_hosts=None,
        ) as conn:
            _ = conn
            pass


@pytest.mark.asyncio
async def test_authorization_expired_session(
    broker_server, test_session_data, db_session
):
    server, port, audit_service, cred_service = broker_server

    # Expire session
    session_model = db_session.get(
        PrivilegedAccessSession, test_session_data["session_id"]
    )
    session_model.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    with pytest.raises(asyncssh.PermissionDenied):
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="ignored",
            password=test_session_data["token"],
            known_hosts=None,
        ) as conn:
            _ = conn
            pass


@pytest.mark.asyncio
async def test_proxy_prevention(broker_server, test_session_data):
    server, port, audit_service, cred_service = broker_server

    import asyncio
    from unittest.mock import AsyncMock, patch

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
            # Try to forward a port. The server should reject it.
            with pytest.raises((asyncssh.ChannelOpenError, asyncssh.Error)):
                await conn.create_connection(asyncio.Protocol, "127.0.0.1", 80)

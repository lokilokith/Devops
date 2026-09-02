"""Brokered SSH Session Worker (Phase 11).

Implements the dedicated SSH broker listener in the Worker Plane.
Authenticates clients via ephemeral session tokens (as passwords),
authorizes connections against the Control/Vault planes, and establishes
bridged I/O streams to real target resources using authorized ephemeral credentials.
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple
from uuid import UUID

import asyncssh
from sqlalchemy import select

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.platform.extensions import db
from app.resources.models import Resource
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding
from app.vault.credential_use import CredentialUseContext, CredentialUseService

logger = logging.getLogger(__name__)

WORKER_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")


class BrokerAuthorizationError(Exception):
    """Raised when session or credential authorization fails."""

    pass


class OpsForgeSSHBroker(asyncssh.SSHServer):
    """AsyncSSH server handling inbound brokered sessions."""

    _active_connections: dict[UUID, asyncssh.SSHServerConnection] = {}

    def __init__(
        self,
        app_context: Any,
        audit_service: AuditService,
        credential_use_service: CredentialUseService,
    ) -> None:
        self._app_context = app_context
        self._audit_service = audit_service
        self._credential_use_service = credential_use_service
        self._session_id: Optional[UUID] = None
        self._target_host: Optional[str] = None
        self._target_port: int = 22
        self._target_username: Optional[str] = None
        self._credential_context: Optional[CredentialUseContext] = None
        self._client_connection: Optional[asyncssh.SSHServerConnection] = None
        self._outbound_connection: Optional[asyncssh.SSHClientConnection] = None

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        self._client_connection = conn
        logger.info(
            f"Broker connection received from {conn.get_extra_info('peername')}"
        )

    def connection_lost(self, exc: Optional[Exception]) -> None:
        logger.info(f"Broker connection lost: {exc}")
        if self._session_id:
            OpsForgeSSHBroker._active_connections.pop(self._session_id, None)

            def _log_disconnect():
                with self._app_context():
                    try:
                        self._audit_service.log_event(
                            actor_user_id=WORKER_ACTOR_ID,
                            action="BROKER_SESSION_TERMINATED",
                            resource_type="privileged_access_sessions",
                            resource_id=str(self._session_id),
                            status=AuditStatus.SUCCESS,
                            severity=AuditSeverity.INFO,
                            details={
                                "reason": "client_disconnect",
                                "exception": str(exc) if exc else None,
                            },
                        )
                        db.session.commit()
                    except Exception:
                        pass

            # Avoid blocking the event loop
            asyncio.create_task(asyncio.to_thread(_log_disconnect))

    def password_auth_supported(self) -> bool:
        """Support password authentication where password = session token."""
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        """Authenticate user by hashing the token and looking up active session."""
        return await asyncio.to_thread(self._sync_validate_and_authorize, password)

    def _sync_validate_and_authorize(self, token: str) -> bool:
        """Synchronous block to perform full authorization chain validation."""
        with self._app_context():
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc)

            # 1. Authoritative session lookup
            session_model = db.session.execute(
                select(PrivilegedAccessSession).where(
                    PrivilegedAccessSession.session_token_hash == token_hash
                )
            ).scalar_one_or_none()

            if not session_model:
                logger.warning("Authentication denied: Unknown token hash.")
                return False

            self._session_id = session_model.id

            if session_model.status not in (
                SessionStatus.PENDING,
                SessionStatus.ACTIVE,
            ):
                logger.warning(
                    f"Authorization denied: Session {session_model.id} is {session_model.status}."
                )
                self._audit_denied("Session status invalid")
                return False

            sess_expires_at = session_model.expires_at
            if sess_expires_at.tzinfo is None:
                sess_expires_at = sess_expires_at.replace(tzinfo=timezone.utc)

            if now > sess_expires_at:
                logger.warning(
                    f"Authorization denied: Session {session_model.id} is expired."
                )
                self._audit_denied("Session expired")
                return False

            # 2. Grant lookup
            grant = db.session.execute(
                select(JITAccessGrant).where(
                    JITAccessGrant.approval_request_id
                    == session_model.access_request_id
                )
            ).scalar_one_or_none()

            if not grant or grant.status != JITGrantStatus.ACTIVE:
                logger.warning(
                    f"Authorization denied: Grant invalid or inactive for session {session_model.id}."
                )
                self._audit_denied("Grant invalid or inactive")
                return False

            grant_expires_at = grant.expires_at
            if grant_expires_at:
                if grant_expires_at.tzinfo is None:
                    grant_expires_at = grant_expires_at.replace(tzinfo=timezone.utc)
                if now > grant_expires_at:
                    logger.warning(
                        f"Authorization denied: Grant expired for session {session_model.id}."
                    )
                    self._audit_denied("Grant expired")
                    return False

            # 3. Target binding lookup
            binding = db.session.get(
                TargetAccountBinding, grant.target_account_binding_id
            )
            if not binding:
                logger.warning(
                    f"Authorization denied: Target binding not found for session {session_model.id}."
                )
                self._audit_denied("Target binding not found")
                return False

            # 4. Resource lookup
            resource = db.session.get(Resource, binding.resource_id)
            if not resource:
                logger.warning(
                    f"Authorization denied: Resource not found for session {session_model.id}."
                )
                self._audit_denied("Resource not found")
                return False

            # Success! Extract authoritative target details and construct credential context
            self._target_host = resource.hostname_ip or resource.resource_code
            self._target_port = resource.port or 22
            self._target_username = binding.target_os_username

            if binding.ssh_credential_id is None:
                logger.warning(
                    f"Authorization denied: No credential bound for session {session_model.id}."
                )
                self._audit_denied("No credential bound")
                return False

            self._credential_context = CredentialUseContext(
                user_id=session_model.user_id,
                resource_id=resource.id,
                credential_id=binding.ssh_credential_id,
                requested_at=now,
                expires_at=session_model.expires_at,
                session_id=session_model.id,
                grant_id=grant.id,
                target_account_binding_id=binding.id,
            )

            # Mark session as active if pending
            if session_model.status == SessionStatus.PENDING:
                session_model.status = SessionStatus.ACTIVE
                session_model.started_at = now

            session_model.last_activity_at = now
            db.session.commit()

            if self._client_connection:
                OpsForgeSSHBroker._active_connections[session_model.id] = (
                    self._client_connection
                )

            self._audit_service.log_event(
                actor_user_id=WORKER_ACTOR_ID,
                action="BROKER_SESSION_CONNECTED",
                resource_type="privileged_access_sessions",
                resource_id=str(session_model.id),
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={"target": self._target_host},
            )
            db.session.commit()

            return True

    def _audit_denied(self, reason: str) -> None:
        """Helper to audit denied attempts."""
        if not self._session_id:
            return
        try:
            self._audit_service.log_event(
                actor_user_id=WORKER_ACTOR_ID,
                action="BROKER_AUTHORIZATION_DENIED",
                resource_type="privileged_access_sessions",
                resource_id=str(self._session_id),
                status=AuditStatus.FAILED,
                severity=AuditSeverity.HIGH,
                details={"reason": reason},
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to audit denial: {e}")

    def server_requested(self, listen_host: str, listen_port: int) -> bool:
        """Reject TCP/IP forwarding requests."""
        return False

    def session_requested(self) -> asyncssh.SSHServerSession:
        """Create the session adapter for interactive shell/commands."""
        return OpsForgeSessionAdapter(self)


class OpsForgeSessionAdapter(asyncssh.SSHServerSession):
    """Bridges the inbound SSH session to the outbound target session."""

    def __init__(self, broker: OpsForgeSSHBroker) -> None:
        self.broker = broker
        self._outbound_process: Optional[asyncssh.SSHClientProcess] = None
        self._outbound_conn: Optional[asyncssh.SSHClientConnection] = None
        self._inbound_channel: Optional[asyncssh.SSHServerChannel] = None
        self._bridge_tasks: list[asyncio.Task] = []
        self._env: dict = {}

    def connection_made(self, chan: asyncssh.SSHServerChannel) -> None:
        self._inbound_channel = chan
        # Start bridging immediately to connect to the target
        asyncio.create_task(self._establish_outbound_connection())

    async def _establish_outbound_connection(self) -> None:
        """Phase 12 Prerequisite: Fetch credential and establish outbound connection."""
        plaintext_credential = None
        try:
            # Run the credential acquisition in a sync thread
            plaintext_credential = await asyncio.to_thread(
                self._sync_acquire_credential
            )

            # Establish the outbound connection to the target
            # Use password if the credential represents one, or load it as a private key
            # For simplicity, if it starts with '-----BEGIN', it's a key, else password.
            pkey = None
            password = None
            cred_str = plaintext_credential.decode("utf-8")
            if "-----BEGIN" in cred_str:
                pkey = asyncssh.import_private_key(cred_str)
            else:
                password = cred_str

            self._outbound_conn = await asyncssh.connect(
                self.broker._target_host,
                port=self.broker._target_port,
                username=self.broker._target_username,
                password=password,
                client_keys=[pkey] if pkey else None,
                known_hosts=None,  # Or use a strict host verifier in production
            )
            self.broker._outbound_connection = self._outbound_conn

            if self._inbound_channel is None:
                raise RuntimeError("No inbound channel available for bridging.")

            # Start interactive shell on outbound
            self._outbound_process = await self._outbound_conn.create_process(
                term_type=self._inbound_channel.get_terminal_type(),
                term_size=self._inbound_channel.get_terminal_size(),
                env=self._env,
            )

            # Bridge stdout/stderr
            self._bridge_tasks.append(
                asyncio.create_task(
                    self._bridge_output(
                        self._outbound_process.stdout, self._inbound_channel
                    )
                )
            )
            self._bridge_tasks.append(
                asyncio.create_task(
                    self._bridge_error(
                        self._outbound_process.stderr, self._inbound_channel.stderr  # type: ignore[attr-defined]
                    )
                )
            )
            # Bridge stdin is handled via data_received callback

        except Exception as e:
            logger.error(f"Failed to establish outbound connection: {e}")
            if self._inbound_channel:
                self._inbound_channel.write(f"Target connection failed: {e}\n")
                self._inbound_channel.close()
        finally:
            # SECURITY: Wipe plaintext credential from memory
            if plaintext_credential:
                del plaintext_credential
            if pkey:
                del pkey
            if password:
                del password

    def _sync_acquire_credential(self) -> bytes:
        """Synchronously acquire the credential via Vault service."""
        with self.broker._app_context():
            if not self.broker._credential_context:
                raise RuntimeError("Credential context is missing.")
            return self.broker._credential_use_service.acquire_ephemeral_credential(
                self.broker._credential_context
            )

    async def _bridge_output(self, stdout, channel: asyncssh.SSHServerChannel) -> None:
        try:
            while not stdout.at_eof():
                data = await stdout.read(4096)
                if data:
                    channel.write(data)
        except Exception:
            pass
        finally:
            channel.close()

    async def _bridge_error(self, stderr, channel_stderr) -> None:
        try:
            while not stderr.at_eof():
                data = await stderr.read(4096)
                if data:
                    channel_stderr.write(data)
        except Exception:
            pass

    def pty_requested(
        self, term_type: str, term_size: tuple[int, int, int, int], term_modes: Mapping[int, int]
    ) -> bool:
        return True

    def terminal_size_changed(
        self, width: int, height: int, pixwidth: int, pixheight: int
    ) -> None:
        if self._outbound_process:
            self._outbound_process.change_terminal_size(
                width, height, pixwidth, pixheight
            )

    def env_requested(self, name: str, value: str) -> bool:
        self._env[name] = value
        return True

    def shell_requested(self) -> bool:
        return True

    def exec_requested(self, command: str) -> bool:
        # For prototype, only interactive shell is fully supported,
        # but single commands can be bridged if implemented. We'll reject exec for simplicity.
        return False

    def data_received(self, data: str, datatype: asyncssh.DataType) -> None:
        if self._outbound_process and self._outbound_process.stdin:
            self._outbound_process.stdin.write(data)

    def eof_received(self) -> bool:
        if self._outbound_process and self._outbound_process.stdin:
            self._outbound_process.stdin.write_eof()
        return False

    def connection_lost(self, exc: Optional[Exception]) -> None:
        for t in self._bridge_tasks:
            t.cancel()
        if self._outbound_conn:
            self._outbound_conn.close()


async def start_expiry_monitor(app_context: Any) -> None:
    """Background task to enforce Layer 1 termination on expired sessions."""
    logger.info("Starting broker expiry monitor loop...")
    while True:
        try:
            await asyncio.sleep(10)
            if not OpsForgeSSHBroker._active_connections:
                continue

            session_ids = list(OpsForgeSSHBroker._active_connections.keys())

            def _get_expired(s_ids):
                with app_context():
                    now = datetime.now(timezone.utc)
                    expired = []
                    for sid in s_ids:
                        session = db.session.get(PrivilegedAccessSession, sid)
                        if session and session.expires_at < now:
                            expired.append(sid)
                    return expired

            expired_ids = await asyncio.to_thread(_get_expired, session_ids)
            for sid in expired_ids:
                conn = OpsForgeSSHBroker._active_connections.get(sid)
                if conn:
                    logger.info(
                        f"Layer-1 Termination: Session {sid} expired. Dropping client connection."
                    )
                    conn.close()
                    # Removal from dictionary happens in connection_lost
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in expiry monitor: {e}")

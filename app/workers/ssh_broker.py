"""Brokered SSH Session Worker (Phase 11).

Implements the dedicated SSH broker listener in the Worker Plane.
Authenticates clients via ephemeral session tokens (as passwords),
authorizes connections against the Control/Vault planes, and establishes
bridged I/O streams to real target resources using authorized ephemeral credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from uuid import UUID

import asyncssh
from sqlalchemy import select

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.host_identity import (
    HostKeyVerifier,
    UntrustedHostError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.platform.extensions import db
from app.resources.models import Resource
from app.sessions.models import PrivilegedAccessSession, SessionStatus
from app.target_accounts.models import TargetAccountBinding
from app.vault.credential_use import CredentialUseContext, CredentialUseService

HARD_MAX_SESSION_TTL = 8 * 3600  # 8 hours

logger = logging.getLogger(__name__)

WORKER_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")


class BrokerAuthorizationError(Exception):
    """Raised when session or credential authorization fails."""

    pass


class OpsForgeSSHBroker(asyncssh.SSHServer):
    """AsyncSSH server handling inbound brokered sessions."""

    _active_connections: dict[UUID, asyncssh.SSHServerConnection] = {}
    _session_locks: dict[UUID, asyncio.Lock] = {}
    _lock_refcounts: dict[UUID, int] = {}

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
        self._host_key_verifier = HostKeyVerifier()

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        self._client_connection = conn
        logger.info(
            f"Broker connection received from {conn.get_extra_info('peername')}"
        )

    @classmethod
    def _get_or_create_lock(cls, session_id: UUID) -> asyncio.Lock:
        if session_id not in cls._session_locks:
            cls._session_locks[session_id] = asyncio.Lock()
            cls._lock_refcounts[session_id] = 0
        cls._lock_refcounts[session_id] += 1
        return cls._session_locks[session_id]

    @classmethod
    def _release_lock_ref(cls, session_id: UUID) -> None:
        if session_id in cls._lock_refcounts:
            cls._lock_refcounts[session_id] -= 1
            if cls._lock_refcounts[session_id] <= 0:
                cls._lock_refcounts.pop(session_id, None)
                cls._session_locks.pop(session_id, None)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        logger.info(f"Broker connection lost: {exc}")
        if self._session_id:
            sid = self._session_id

            async def _safe_cleanup():
                lock = self._get_or_create_lock(sid)
                try:
                    async with lock:
                        if (
                            OpsForgeSSHBroker._active_connections.get(sid)
                            == self._client_connection
                        ):
                            OpsForgeSSHBroker._active_connections.pop(sid, None)
                finally:
                    self._release_lock_ref(sid)

            asyncio.create_task(_safe_cleanup())

            def _log_disconnect():
                with self._app_context():
                    try:
                        self._audit_service.log_event(
                            actor_user_id=WORKER_ACTOR_ID,
                            action="BROKER_SESSION_TERMINATED",
                            resource_type="privileged_access_sessions",
                            resource_id=str(sid),
                            status=AuditStatus.SUCCESS,
                            severity=AuditSeverity.INFO,
                            details={
                                "reason": "client_disconnect",
                                "exception": str(exc) if exc else None,
                            },
                        )
                        db.session.commit()
                    except Exception as logging_exc:
                        logger.error(
                            f"Failed to log disconnect audit event: {logging_exc}"
                        )

            # Avoid blocking the event loop
            asyncio.create_task(asyncio.to_thread(_log_disconnect))

    def password_auth_supported(self) -> bool:
        """Support password authentication where password = session token."""
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        """Authenticate user by hashing the token and looking up active session."""
        session_id = await asyncio.to_thread(
            self._sync_validate_and_authorize, password
        )
        if not session_id:
            return False

        # Phase 12: Process-local critical section for connection registration
        lock = self._get_or_create_lock(session_id)
        try:
            async with lock:
                if session_id in OpsForgeSSHBroker._active_connections:
                    logger.warning(
                        f"Authorization denied: Duplicate connection rejected for session {session_id}"
                    )
                    return False

                if self._client_connection:
                    OpsForgeSSHBroker._active_connections[session_id] = (
                        self._client_connection
                    )
                return True
        finally:
            self._release_lock_ref(session_id)

    def _sync_validate_and_authorize(self, token: str) -> Optional[UUID]:
        """Synchronous block to perform full authorization chain validation."""
        with self._app_context():
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc)

            # 1. Authoritative session lookup
            session_model = db.session.execute(
                select(PrivilegedAccessSession)
                .where(PrivilegedAccessSession.session_token_hash == token_hash)
                .with_for_update()
            ).scalar_one_or_none()

            if not session_model:
                logger.warning("Authentication denied: Unknown token hash.")
                return None

            self._session_id = session_model.id

            if session_model.status not in (
                SessionStatus.PENDING,
                SessionStatus.ACTIVE,
            ):
                logger.warning(
                    f"Authorization denied: Session {session_model.id} is {session_model.status}."
                )
                self._audit_denied("Session status invalid")
                return None

            sess_expires_at = session_model.expires_at
            if sess_expires_at.tzinfo is None:
                sess_expires_at = sess_expires_at.replace(tzinfo=timezone.utc)

            # 2. Grant lookup
            grant = db.session.execute(
                select(JITAccessGrant)
                .where(
                    JITAccessGrant.approval_request_id
                    == session_model.access_request_id
                )
                .with_for_update()
            ).scalar_one_or_none()

            if not grant or grant.status != JITGrantStatus.ACTIVE:
                logger.warning(
                    f"Authorization denied: Grant invalid or inactive for session {session_model.id}."
                )
                self._audit_denied("Grant invalid or inactive")
                return None

            grant_expires_at = grant.expires_at
            if grant_expires_at:
                if grant_expires_at.tzinfo is None:
                    grant_expires_at = grant_expires_at.replace(tzinfo=timezone.utc)
            else:
                grant_expires_at = now + timedelta(seconds=HARD_MAX_SESSION_TTL)

            session_creation = session_model.started_at or now
            if session_creation.tzinfo is None:
                session_creation = session_creation.replace(tzinfo=timezone.utc)

            hard_limit = session_creation + timedelta(seconds=HARD_MAX_SESSION_TTL)

            # Enforce Hard TTL: session cannot outlive grant, and cannot outlive hard limit
            effective_expires_at = min(sess_expires_at, grant_expires_at, hard_limit)
            session_model.expires_at = effective_expires_at

            if now > effective_expires_at:
                logger.warning(
                    f"Authorization denied: Session {session_model.id} is expired (Hard TTL enforced)."
                )
                self._audit_denied("Session expired")
                return None

            # 3. Target binding lookup
            binding = db.session.get(
                TargetAccountBinding, grant.target_account_binding_id
            )
            if not binding:
                logger.warning(
                    f"Authorization denied: Target binding not found for session {session_model.id}."
                )
                self._audit_denied("Target binding not found")
                return None

            # 4. Resource lookup
            resource = db.session.get(Resource, binding.resource_id)
            if not resource:
                logger.warning(
                    f"Authorization denied: Resource not found for session {session_model.id}."
                )
                self._audit_denied("Resource not found")
                return None

            # Success! Extract authoritative target details and construct credential context
            self._target_host = resource.hostname_ip or resource.resource_code
            self._target_port = resource.port or 22
            self._target_username = binding.target_os_username

            if resource.pinned_host_key:
                try:
                    parts = resource.pinned_host_key.split()
                    if len(parts) >= 2:
                        self._host_key_verifier.register_trusted_key(
                            host=self._target_host,
                            key_type=parts[0],
                            key_base64=parts[1],
                        )
                except Exception as e:
                    logger.warning(f"Failed to register pinned host key: {e}")

            if binding.ssh_credential_id is None:
                logger.warning(
                    f"Authorization denied: No credential bound for session {session_model.id}."
                )
                self._audit_denied("No credential bound")
                return None

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

            return session_model.id

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

    def connection_requested(
        self, dest_host: str, dest_port: int, orig_host: str, orig_port: int
    ) -> bool:
        """Reject direct-tcpip requests."""
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
        pkey = None
        password = None
        try:
            # Run the credential acquisition in a sync thread
            plaintext_credential = await asyncio.to_thread(
                self._sync_acquire_credential
            )

            # Establish the outbound connection to the target
            # asyncssh expects raw key data as bytes, otherwise it treats strings as file paths.
            client_keys: Optional[list[bytes]] = None
            if plaintext_credential and b"-----BEGIN" not in plaintext_credential:
                password = plaintext_credential.decode("utf-8")
            elif plaintext_credential:
                client_keys = [plaintext_credential]

            if not self.broker._target_host:
                raise RuntimeError("Target host is not configured.")

            trusted = self.broker._host_key_verifier.get_trusted_key(
                self.broker._target_host
            )
            if not trusted:
                logger.error(
                    f"Host key verification failed: Untrusted target host '{self.broker._target_host}'"
                )
                raise UntrustedHostError("Target host is not trusted")

            if self.broker._target_port != 22:
                host_str = f"[{self.broker._target_host}]:{self.broker._target_port}"
            else:
                host_str = self.broker._target_host
            known_hosts_line = f"{host_str} {trusted.key_type} {trusted.key_base64}"
            known_hosts = asyncssh.import_known_hosts(known_hosts_line)

            self._outbound_conn = await asyncssh.connect(
                self.broker._target_host,
                port=self.broker._target_port,
                username=self.broker._target_username,
                password=password,
                client_keys=client_keys,
                known_hosts=known_hosts,
            )

            # Delete reference to sensitive material
            if plaintext_credential is not None:
                del plaintext_credential
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
                        self._outbound_process.stderr, self._inbound_channel
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
            # We delete references to credential material.
            # Note: Python's memory management does not guarantee secure zeroization.
            if pkey is not None:
                del pkey
            if password is not None:
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
        except (
            asyncssh.Error,
            asyncio.IncompleteReadError,
            ConnectionResetError,
            OSError,
        ):
            pass
        except Exception as e:
            logger.warning(f"Unexpected error in stdout bridge: {e}")
        finally:
            channel.close()

    async def _bridge_error(self, stderr, channel: asyncssh.SSHServerChannel) -> None:
        try:
            while not stderr.at_eof():
                data = await stderr.read(4096)
                if data:
                    channel.write_stderr(data)
        except (
            asyncssh.Error,
            asyncio.IncompleteReadError,
            ConnectionResetError,
            OSError,
        ):
            pass
        except Exception as e:
            logger.warning(f"Unexpected error in stderr bridge: {e}")

    def pty_requested(
        self,
        term_type: str,
        term_size: tuple[int, int, int, int],
        term_modes: Mapping[int, int],
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

    def x11_requested(
        self,
        single_connection: bool,
        auth_protocol: str,
        auth_cookie: str,
        screen_number: int,
    ) -> bool:
        return False

    def agent_requested(self) -> bool:
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


def sweep_expired_sessions(app_context: Any, session_ids: list[UUID]) -> list[UUID]:
    """Helper to evaluate authoritative expiration of active sessions."""
    with app_context():
        now = datetime.now(timezone.utc)
        expired = []
        for sid in session_ids:
            session = db.session.get(PrivilegedAccessSession, sid)
            if not session:
                continue

            sess_expires_at = session.expires_at
            if sess_expires_at.tzinfo is None:
                sess_expires_at = sess_expires_at.replace(tzinfo=timezone.utc)

            creation_time = session.started_at or (
                sess_expires_at - timedelta(seconds=HARD_MAX_SESSION_TTL)
            )
            if creation_time.tzinfo is None:
                creation_time = creation_time.replace(tzinfo=timezone.utc)

            hard_limit = creation_time + timedelta(seconds=HARD_MAX_SESSION_TTL)
            effective_expires_at = min(sess_expires_at, hard_limit)

            if effective_expires_at < now:
                expired.append(sid)
                continue

            # Check authoritative grant status for revocation
            grant = db.session.execute(
                select(JITAccessGrant).where(
                    JITAccessGrant.approval_request_id == session.access_request_id
                )
            ).scalar_one_or_none()

            if grant and grant.status in (
                JITGrantStatus.REVOKED,
                JITGrantStatus.REVOCATION_PENDING,
                JITGrantStatus.EXPIRED,
                JITGrantStatus.DENIED,
                JITGrantStatus.FAILED,
                JITGrantStatus.SECURITY_UNCERTAIN,
            ):
                expired.append(sid)

        return expired


async def start_expiry_monitor(app_context: Any) -> None:
    """Background task to enforce Layer 1 termination on expired sessions."""
    logger.info("Starting broker expiry monitor loop...")
    while True:
        try:
            await asyncio.sleep(10)
            if not OpsForgeSSHBroker._active_connections:
                continue

            session_ids = list(OpsForgeSSHBroker._active_connections.keys())

            expired_ids = await asyncio.to_thread(
                sweep_expired_sessions, app_context, session_ids
            )
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

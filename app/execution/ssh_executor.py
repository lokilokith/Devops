"""SSH Target Executor for OpsForge Execution Plane.

Implements real SSH connection lifecycle, resolve-once network validation,
strict host-key pinning and verification, deterministic error mapping,
concurrency/resource safety, and strict credential non-disclosure.
"""

from __future__ import annotations

import base64
import io
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Set
from uuid import UUID

import paramiko

from app.execution.audit import ExecutionAuditService
from app.execution.domain import (
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.execution.exceptions import (
    ExecutionError,
    ExecutionTimeoutError,
    InvalidExecutionContextError,
    TargetAuthenticationError,
    TransportError,
)
from app.execution.host_identity import (
    HostKeyMismatchError,
    HostKeyVerificationError,
    HostKeyVerifier,
    UntrustedHostError,
)
from app.execution.network_validator import (
    TargetAddressValidationError,
    TargetAddressValidator,
    ValidatedTargetDestination,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SSHExecutionConfig:
    """Configuration options for SSH Target Executor."""

    connect_timeout: float = 10.0
    banner_timeout: float = 10.0
    auth_timeout: float = 10.0
    max_concurrent_connections: int = 10
    connection_pool_timeout: float = 5.0
    allow_loopback: bool = False
    allowed_ports: Set[int] = field(default_factory=lambda: {22, 2222})
    auto_trust_on_first_use: bool = False


class _OpsForgeMissingHostKeyPolicy(paramiko.client.MissingHostKeyPolicy):
    """Paramiko host key policy enforcing OpsForge HostKeyVerifier rules."""

    def __init__(
        self,
        verifier: HostKeyVerifier,
        auto_trust: bool = False,
        audit_service: Optional[ExecutionAuditService] = None,
        resource_id: Optional[UUID] = None,
        execution_id: Optional[UUID] = None,
    ) -> None:
        self._verifier = verifier
        self._auto_trust = auto_trust
        self._audit_service = audit_service
        self._resource_id = resource_id
        self._execution_id = execution_id

    def missing_host_key(
        self,
        client: paramiko.SSHClient,
        hostname: str,
        key: paramiko.PKey,
    ) -> None:
        key_type = key.get_name()
        key_bytes = key.asbytes()
        fingerprint = HostKeyVerifier.compute_sha256_fingerprint(key_bytes)
        key_b64 = base64.b64encode(key_bytes).decode("ascii")

        # Normalize hostname (Paramiko passes [host]:port for non-standard ports)
        trusted = self._verifier.get_trusted_key(hostname)
        if trusted is None:
            # Try stripping [ ] and :port
            clean_host = hostname.strip("[]")
            if ":" in clean_host:
                clean_host = clean_host.split("]:")[0].split(":")[0]
            trusted = self._verifier.get_trusted_key(clean_host)
        if trusted is not None:
            # We already have a trusted key recorded; check for mismatch
            if trusted.key_type != key_type or trusted.key_base64 != key_b64:
                err_msg = (
                    f"HOST KEY MISMATCH DETECTED for '{hostname}'! "
                    f"Expected fingerprint {trusted.fingerprint_sha256}, got {fingerprint}. "
                    "Possible Man-in-the-Middle attack. Connection aborted."
                )
                raise HostKeyMismatchError(err_msg)
            return

        # Untrusted host
        if self._auto_trust:
            self._verifier.register_trusted_key(hostname, key_type, key_b64)
            return

        err_msg = (
            f"Untrusted target host '{hostname}'. No registered host key found. "
            f"Presented fingerprint: {fingerprint}. Connection rejected."
        )
        raise UntrustedHostError(err_msg)


class SSHConnectionContext:
    """Safe, leak-proof context manager for SSH connections.

    Enforces:
    1. Resolve-once DNS resolution with direct IP socket connection.
    2. Strict SSRF blocking before opening network socket.
    3. Host-key verification and fail-closed mismatch protection.
    4. In-memory private key loading (zero temporary files or disk caching).
    5. Clean disconnect and socket closure on exit.
    6. Concurrency limiting and resource protection.
    """

    def __init__(
        self,
        target_host: str,
        target_port: int,
        username: str,
        private_key_pem: Optional[str | bytes] = None,
        private_key_passphrase: Optional[str] = None,
        password: Optional[str] = None,
        network_validator: Optional[TargetAddressValidator] = None,
        host_key_verifier: Optional[HostKeyVerifier] = None,
        config: Optional[SSHExecutionConfig] = None,
        resource_id: Optional[UUID] = None,
        execution_id: Optional[UUID] = None,
        audit_service: Optional[ExecutionAuditService] = None,
        semaphore: Optional[threading.Semaphore] = None,
    ) -> None:
        self.target_host = target_host
        self.target_port = target_port
        self.username = username
        self._private_key_pem = private_key_pem
        self._private_key_passphrase = private_key_passphrase
        self._password = password
        self.config = config or SSHExecutionConfig()
        self.network_validator = network_validator or TargetAddressValidator(
            allow_loopback=self.config.allow_loopback,
            allowed_ports=self.config.allowed_ports,
        )
        self.host_key_verifier = host_key_verifier or HostKeyVerifier()
        self.resource_id = resource_id
        self.execution_id = execution_id
        self.audit_service = audit_service
        self._semaphore = semaphore

        self._client: Optional[paramiko.SSHClient] = None
        self._socket: Optional[socket.socket] = None
        self._acquired_semaphore: bool = False
        self.validated_destination: Optional[ValidatedTargetDestination] = None

    def __enter__(self) -> paramiko.SSHClient:
        # 1. Concurrency limit acquisition
        if self._semaphore is not None:
            acquired = self._semaphore.acquire(
                timeout=self.config.connection_pool_timeout
            )
            if not acquired:
                raise ExecutionTimeoutError(
                    f"Connection concurrency limit ({self.config.max_concurrent_connections}) reached. "
                    f"Timed out waiting for connection slot.",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                )
            self._acquired_semaphore = True

        try:
            # 2. Resolve-once target validation
            try:
                self.validated_destination = (
                    self.network_validator.validate_destination(
                        self.target_host, self.target_port
                    )
                )
            except TargetAddressValidationError as e:
                raise TransportError(
                    f"Target address validation rejected destination {self.target_host}:{self.target_port}: {e}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e

            # 3. Create raw TCP socket directly to validated IP (resolve-once discipline)
            try:
                self._socket = socket.create_connection(
                    (
                        self.validated_destination.resolved_ip,
                        self.validated_destination.port,
                    ),
                    timeout=self.config.connect_timeout,
                )
            except (socket.timeout, TimeoutError) as e:
                raise ExecutionTimeoutError(
                    f"Connection timed out establishing TCP socket to "
                    f"{self.validated_destination.resolved_ip}:{self.validated_destination.port}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e
            except (socket.error, OSError) as e:
                raise TransportError(
                    f"Network error connecting to {self.validated_destination.resolved_ip}: {e}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e

            # 4. Initialize Paramiko SSHClient with strict host key verifier
            self._client = paramiko.SSHClient()
            policy = _OpsForgeMissingHostKeyPolicy(
                verifier=self.host_key_verifier,
                auto_trust=self.config.auto_trust_on_first_use,
                audit_service=self.audit_service,
                resource_id=self.resource_id,
                execution_id=self.execution_id,
            )
            self._client.set_missing_host_key_policy(policy)

            # 5. Load private key in-memory if provided
            pkey = None
            if self._private_key_pem:
                pkey = self._load_private_key(
                    self._private_key_pem, self._private_key_passphrase
                )

            # 6. Establish SSH connection over validated socket
            try:
                self._client.connect(
                    hostname=self.target_host,
                    port=self.validated_destination.port,
                    username=self.username,
                    password=self._password,
                    pkey=pkey,
                    sock=self._socket,
                    timeout=self.config.connect_timeout,
                    banner_timeout=self.config.banner_timeout,
                    auth_timeout=self.config.auth_timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
            except (HostKeyMismatchError, UntrustedHostError) as e:
                raise e
            except paramiko.AuthenticationException as e:
                raise TargetAuthenticationError(
                    f"SSH authentication failed for user '{self.username}' on {self.target_host}: {e}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e
            except paramiko.BadHostKeyException as e:
                raise HostKeyMismatchError(
                    f"Host key mismatch for {self.target_host}: {e}"
                ) from e
            except (socket.timeout, TimeoutError) as e:
                raise ExecutionTimeoutError(
                    f"SSH handshake timed out connecting to {self.target_host}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e
            except paramiko.SSHException as e:
                raise TransportError(
                    f"SSH protocol error connecting to {self.target_host}: {e}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e
            except Exception as e:
                raise TransportError(
                    f"Unexpected error during SSH connection: {e}",
                    resource_id=self.resource_id,
                    execution_id=self.execution_id,
                ) from e

            return self._client

        except Exception:
            self._cleanup()
            raise

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        """Safely close client and underlying socket and release concurrency semaphore."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._acquired_semaphore and self._semaphore is not None:
            try:
                self._semaphore.release()
            except Exception:
                pass
            self._acquired_semaphore = False

    @staticmethod
    def _load_private_key(
        key_data: str | bytes, passphrase: Optional[str] = None
    ) -> paramiko.PKey:
        """Load private key from in-memory string or bytes across key algorithms."""
        if isinstance(key_data, bytes):
            key_str = key_data.decode("utf-8", errors="replace")
        else:
            key_str = key_data

        key_file = io.StringIO(key_str.strip())
        key_classes = [
            paramiko.Ed25519Key,
            paramiko.RSAKey,
            paramiko.ECDSAKey,
        ]

        last_error = None
        for cls in key_classes:
            key_file.seek(0)
            try:
                return cls.from_private_key(key_file, password=passphrase)
            except Exception as e:
                last_error = e

        raise TargetAuthenticationError(
            f"Failed to parse private key material (unsupported or invalid format): {last_error}"
        )


class SSHTargetExecutor:
    """Real SSH TargetExecutor implementation adhering to the Execution Plane contract."""

    def __init__(
        self,
        config: Optional[SSHExecutionConfig] = None,
        network_validator: Optional[TargetAddressValidator] = None,
        host_key_verifier: Optional[HostKeyVerifier] = None,
        audit_service: Optional[ExecutionAuditService] = None,
        resource_resolver: Optional[Callable[[UUID], Optional[Any]]] = None,
    ) -> None:
        self.config = config or SSHExecutionConfig()
        self.network_validator = network_validator or TargetAddressValidator(
            allow_loopback=self.config.allow_loopback,
            allowed_ports=self.config.allowed_ports,
        )
        self.host_key_verifier = host_key_verifier or HostKeyVerifier()
        self.audit_service = audit_service
        self.resource_resolver = resource_resolver
        self._semaphore = threading.Semaphore(self.config.max_concurrent_connections)

    def can_execute(
        self, resource_id: UUID, operation: Optional[ExecutionOperation] = None
    ) -> bool:
        """Return True if executor handles SSH operations for the resource."""
        if operation is not None and operation != ExecutionOperation.VALIDATE_TARGET:
            # In Phase 3, we strictly provide connection and target validation
            return False

        if self.resource_resolver is not None:
            res = self.resource_resolver(resource_id)
            if res is not None:
                proto = getattr(res, "protocol", None) or getattr(
                    res, "connection_method", None
                )
                if proto:
                    return str(proto).lower() in ("ssh", "connectionmethod.ssh")
        return True

    def validate_target(self, request: ExecutionRequest) -> ExecutionResult:
        """Verify target reachability, host identity, and network trust boundaries via real SSH."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        # Extract connection parameters from request parameters or resource
        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        username = params.get("username") or "opsforge-svc"
        private_key = params.get("private_key")
        password = params.get("password")

        # Fallback to resource resolver if host/port not in parameters
        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                # If resource has pinned host key, register in verifier
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if not host:
            raise InvalidExecutionContextError(
                f"Missing target hostname or IP for resource {request.resource_id}",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=private_key,
                password=password,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                transport = client.get_transport()
                if transport is None or not transport.is_active():
                    raise TransportError(
                        f"SSH transport is inactive after handshake for {host}",
                        resource_id=request.resource_id,
                        execution_id=request.execution_id,
                    )

                duration_ms = (time.monotonic() - start_time) * 1000.0

                result = ExecutionResult(
                    execution_id=request.execution_id,
                    operation=ExecutionOperation.VALIDATE_TARGET,
                    status=ExecutionStatus.SUCCESS,
                    verification_status=VerificationStatus.VERIFIED_SUCCESS,
                    details={
                        "host": host,
                        "port": port,
                        "username": username,
                        "status": "connected_and_verified",
                    },
                    duration_ms=duration_ms,
                )

                if self.audit_service:
                    try:
                        self.audit_service.record_execution_event(request, result)
                    except Exception:
                        pass

                return result

        except ExecutionError as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            classification = FailureClassification.TARGET_FAILURE
            if isinstance(e, TargetAuthenticationError) or isinstance(
                e, HostKeyVerificationError
            ):
                classification = FailureClassification.AUTHENTICATION_FAILURE
            elif isinstance(e, ExecutionTimeoutError):
                classification = FailureClassification.TIMEOUT
            elif isinstance(e, TransportError):
                classification = FailureClassification.TRANSPORT_FAILURE

            failed_result = ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.VALIDATE_TARGET,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=classification,
                error_message=e.sanitized_message,
                details={"host": host, "port": port},
                duration_ms=duration_ms,
            )

            if self.audit_service:
                try:
                    self.audit_service.record_execution_event(request, failed_result)
                except Exception:
                    pass

            return failed_result

    def provision_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 4+ operation - guarded by Phase 3 strict boundary."""
        raise NotImplementedError(
            "provision_account is a Phase 6 operation and is not permitted in Phase 3."
        )

    def remove_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 4+ operation - guarded by Phase 3 strict boundary."""
        raise NotImplementedError(
            "remove_account is a Phase 6 operation and is not permitted in Phase 3."
        )

    def rotate_credential(
        self, request: ExecutionRequest, current_secret: bytes
    ) -> ExecutionResult:
        """Phase 4+ operation - guarded by Phase 3 strict boundary."""
        raise NotImplementedError(
            "rotate_credential is a Phase 4 operation and is not permitted in Phase 3."
        )

    def apply_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 4+ operation - guarded by Phase 3 strict boundary."""
        raise NotImplementedError(
            "apply_jit_grant is a Phase 7 operation and is not permitted in Phase 3."
        )

    def revoke_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 4+ operation - guarded by Phase 3 strict boundary."""
        raise NotImplementedError(
            "revoke_jit_grant is a Phase 8 operation and is not permitted in Phase 3."
        )

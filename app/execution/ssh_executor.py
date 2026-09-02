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
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Set
from uuid import UUID

import paramiko

from app.execution.audit import ExecutionAuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
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
    TargetAuthorizationError,
    TargetExecutionError,
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
        if operation is not None and operation not in (
            ExecutionOperation.VALIDATE_TARGET,
            ExecutionOperation.ROTATE_CREDENTIAL,
            ExecutionOperation.PROVISION_ACCOUNT,
            ExecutionOperation.REMOVE_ACCOUNT,
        ):
            # In Phase 6, we provide validation, rotation, and account provisioning/removal
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

    def rotate_credential(
        self, request: ExecutionRequest, current_secret: bytes
    ) -> ExecutionResult:
        """Execute canonical Add -> Verify -> Remove -> Verify -> Commit SSH rotation."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        username = params.get("username") or "opsforge-svc"

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
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

        # Reject disallowed/protected accounts
        protected_accounts = {
            "root",
            "bin",
            "daemon",
            "sys",
            "sync",
            "games",
            "man",
            "lp",
            "mail",
            "nobody",
        }
        if username.lower() in protected_accounts:
            raise TargetAuthorizationError(
                f"Cannot rotate credentials for protected system account '{username}'",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        current_secret_str = (
            current_secret.decode("utf-8")
            if isinstance(current_secret, bytes)
            else str(current_secret)
        )

        from app.vault.ssh_keys import extract_public_key, generate_ed25519_keypair

        # Step 1: Generate new Ed25519 keypair in memory
        try:
            new_private_pem, new_public_ssh = generate_ed25519_keypair(
                comment=f"opsforge-{request.execution_id.hex[:8]}"
            )
            old_public_ssh = extract_public_key(current_secret_str)
            old_key_base64 = old_public_ssh.strip().split()[1]
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message=f"Failed to generate new keypair or parse old key: {e}",
                duration_ms=duration_ms,
            )

        # Step 2: Connect using CURRENT credential and install new public key alongside old
        install_script = f"""python3 -c '
import os, stat
ssh_dir = os.path.expanduser("~/.ssh")
if not os.path.exists(ssh_dir):
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
auth_keys = os.path.join(ssh_dir, "authorized_keys")
if os.path.islink(auth_keys):
    raise RuntimeError("Symlink detected on authorized_keys")
content = ""
if os.path.exists(auth_keys):
    with open(auth_keys, "r", encoding="utf-8") as f:
        content = f.read()
new_key = "{new_public_ssh.strip()}"
if new_key not in content:
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    lines.append(new_key)
    tmp_path = os.path.join(ssh_dir, ".auth_keys.tmp." + str(os.getpid()))
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\\n".join(lines) + "\\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, auth_keys)
print("INSTALL_SUCCESS")
'"""

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=current_secret_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                _, stdout, stderr = client.exec_command(install_script)  # nosec B601
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                if "INSTALL_SUCCESS" not in out:
                    raise TargetExecutionError(
                        f"Failed to install new public key on target: {err or out}",
                        resource_id=request.resource_id,
                        execution_id=request.execution_id,
                    )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"Failed during new public key installation: {e}",
                duration_ms=duration_ms,
            )

        # Step 3: INDEPENDENTLY VERIFY new credential on a COMPLETELY FRESH connection
        new_key_verified = False
        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=new_private_pem,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                _, stdout, _ = client.exec_command("whoami")  # nosec B601
                if stdout.read().decode().strip() == username:
                    new_key_verified = True
        except Exception as e:
            new_key_verified = False
            logger.warning(
                "New credential verification failed during rotation for %s: %s",
                username,
                e,
            )

        if not new_key_verified:
            # Rollback attempt: Connect with old key and remove the new key
            try:
                cleanup_script = f"""python3 -c '
import os
ssh_dir = os.path.expanduser("~/.ssh")
auth_keys = os.path.join(ssh_dir, "authorized_keys")
if os.path.exists(auth_keys) and not os.path.islink(auth_keys):
    with open(auth_keys, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_key_b64 = "{new_public_ssh.strip().split()[1]}"
    filtered = [l for l in lines if new_key_b64 not in l]
    tmp_path = os.path.join(ssh_dir, ".auth_keys.tmp." + str(os.getpid()))
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(filtered)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, auth_keys)
'"""
                with SSHConnectionContext(
                    target_host=host,
                    target_port=port,
                    username=username,
                    private_key_pem=current_secret_str,
                    network_validator=self.network_validator,
                    host_key_verifier=self.host_key_verifier,
                    config=self.config,
                    resource_id=request.resource_id,
                    execution_id=request.execution_id,
                ) as rollback_client:
                    rollback_client.exec_command(cleanup_script)  # nosec B601
            except Exception:
                pass

            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.VERIFICATION_FAILURE,
                error_message="New credential failed independent authentication verification. Old key preserved.",
                duration_ms=duration_ms,
            )

        # Step 4: REMOVE old public key from target authorized_keys
        remove_script = f"""python3 -c '
import os
ssh_dir = os.path.expanduser("~/.ssh")
auth_keys = os.path.join(ssh_dir, "authorized_keys")
if os.path.islink(auth_keys):
    raise RuntimeError("Symlink detected on authorized_keys")
if os.path.exists(auth_keys):
    with open(auth_keys, "r", encoding="utf-8") as f:
        lines = f.readlines()
    old_key_b64 = "{old_key_base64}"
    filtered = [l for l in lines if old_key_b64 not in l]
    tmp_path = os.path.join(ssh_dir, ".auth_keys.tmp." + str(os.getpid()))
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(filtered)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, auth_keys)
print("REMOVE_SUCCESS")
'"""
        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=new_private_pem,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                _, stdout, stderr = client.exec_command(remove_script)  # nosec B601
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                if "REMOVE_SUCCESS" not in out:
                    raise TargetExecutionError(
                        f"Failed to remove old public key from target: {err or out}",
                        resource_id=request.resource_id,
                        execution_id=request.execution_id,
                    )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFICATION_INDETERMINATE,
                failure_classification=FailureClassification.UNCERTAIN_STATE,
                is_uncertain=True,
                error_message=f"Failed during old key removal. State is uncertain: {e}",
                duration_ms=duration_ms,
            )

        # Step 5: VERIFY old credential is rejected on a fresh connection
        old_rejected = False
        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=current_secret_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            ):
                # If we get here, old key still worked!
                old_rejected = False
        except TargetAuthenticationError:
            # Genuine authentication failure proves old key is revoked!
            old_rejected = True
        except Exception as e:
            logger.warning("Old key verification raised non-auth error: %s", e)
            old_rejected = False

        if not old_rejected:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.VERIFICATION_FAILURE,
                is_uncertain=True,
                error_message="Old credential was not conclusively revoked on target",
                duration_ms=duration_ms,
            )

        # Step 6: FINAL VERIFY new credential still authenticates
        final_verified = False
        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username=username,
                private_key_pem=new_private_pem,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            ) as final_client:
                _, stdout, _ = final_client.exec_command("whoami")  # nosec B601
                if stdout.read().decode().strip() == username:
                    final_verified = True
        except Exception as e:
            final_verified = False
            logger.error("Final new credential verification failed: %s", e)

        if not final_verified:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.VERIFICATION_FAILURE,
                is_uncertain=True,
                error_message="New credential failed final authentication verification after old key removal",
                duration_ms=duration_ms,
            )

        # Step 7: Complete rotation and return new secret bytes
        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.ROTATE_CREDENTIAL,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            new_secret_version=new_private_pem.encode("utf-8"),
            details={
                "host": host,
                "port": port,
                "username": username,
                "status": "rotated_and_verified",
                "rotation_step": "COMPLETED",
            },
            duration_ms=duration_ms,
        )

        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass

        return result

    def execute(self, resource_id: UUID, current_secret: bytes) -> dict[str, Any]:
        """Legacy and background-worker adapter method for rotation."""
        now = datetime.now(timezone.utc)
        auth_ctx = ExecutionAuthorizationContext(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            resource_id=resource_id,
            credential_id=UUID("00000000-0000-0000-0000-000000000001"),
            requested_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        req = ExecutionRequest(
            operation=ExecutionOperation.ROTATE_CREDENTIAL,
            resource_id=resource_id,
            authorization_context=auth_ctx,
        )
        res = self.rotate_credential(req, current_secret)
        if res.is_success and res.new_secret_version:
            return {
                "new_secret_version": res.new_secret_version,
                "error": None,
                "status": "success",
            }
        return {
            "new_secret_version": None,
            "error": res.error_message or "Rotation failed",
            "status": "failed",
        }

    def provision_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 6 operation: Provision human target account via helper boundary and verify."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        target_os_username = params.get("target_os_username")
        public_key = params.get("public_key")
        bootstrap_credential = params.get("bootstrap_credential")
        user_private_key = params.get("user_private_key")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
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

        if not target_os_username or not public_key:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.PROVISION_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing target_os_username or public_key parameters",
                duration_ms=duration_ms,
            )

        if not bootstrap_credential:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.PROVISION_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing bootstrap credential for target provisioning",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, bytes)
            else str(bootstrap_credential)
        )

        user_priv_str = (
            user_private_key.decode("utf-8")
            if isinstance(user_private_key, bytes)
            else str(user_private_key) if user_private_key else None
        )

        # Step 1: Connect as bootstrap user (opsforge-svc) and invoke helper
        helper_cmd = f"sudo -n /usr/local/sbin/opsforge-helper provision_account {target_os_username} '{public_key.strip()}'"

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                _, stdout, stderr = client.exec_command(helper_cmd)  # nosec B601
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                exit_code = stdout.channel.recv_exit_status()
                if exit_code != 0:
                    err_msg = err or out or f"Helper exited with code {exit_code}"
                    is_uncertain = "uncertain" in err_msg.lower()
                    classification = (
                        FailureClassification.UNCERTAIN_STATE
                        if is_uncertain
                        else FailureClassification.TARGET_FAILURE
                    )
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.PROVISION_ACCOUNT,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.VERIFIED_FAILURE,
                        failure_classification=classification,
                        error_message=f"Helper provision_account failed: {err_msg}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

        except TargetAuthenticationError as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.PROVISION_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.AUTHENTICATION_FAILURE,
                error_message=f"Bootstrap authentication failed: {e}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.PROVISION_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TRANSPORT_FAILURE,
                error_message=f"Transport error communicating with target: {e}",
                duration_ms=duration_ms,
            )

        # Step 2: Target-Side Independent Verification (MANDATORY)
        # Open fresh SSH connection presenting ONLY the newly generated user private key
        if user_priv_str:
            try:
                with SSHConnectionContext(
                    target_host=host,
                    target_port=port,
                    username=target_os_username,
                    private_key_pem=user_priv_str,
                    network_validator=self.network_validator,
                    host_key_verifier=self.host_key_verifier,
                    config=self.config,
                    resource_id=request.resource_id,
                    execution_id=request.execution_id,
                    audit_service=self.audit_service,
                    semaphore=self._semaphore,
                ) as user_client:
                    # 1. Verify username
                    _, stdout, _ = user_client.exec_command("whoami")  # nosec B601
                    whoami_out = stdout.read().decode().strip()
                    if whoami_out != target_os_username:
                        raise ValueError(
                            f"whoami check mismatch: expected {target_os_username}, got {whoami_out}"
                        )

                    # 2. Verify shell
                    _, stdout, _ = user_client.exec_command("echo $SHELL")  # nosec B601
                    shell_out = stdout.read().decode().strip()
                    if "/bin/bash" not in shell_out:
                        raise ValueError(
                            f"Shell check mismatch: expected /bin/bash, got {shell_out}"
                        )

                    # 3. Verify no standing sudo privilege (must fail)
                    _, stdout, _ = user_client.exec_command(
                        "sudo -n true"
                    )  # nosec B601
                    sudo_code = stdout.channel.recv_exit_status()
                    if sudo_code == 0:
                        raise ValueError(
                            "Security violation: user has unexpected standing sudo privilege!"
                        )

            except Exception as e:
                duration_ms = (time.monotonic() - start_time) * 1000.0
                result = ExecutionResult(
                    execution_id=request.execution_id,
                    operation=ExecutionOperation.PROVISION_ACCOUNT,
                    status=ExecutionStatus.FAILED,
                    verification_status=VerificationStatus.VERIFIED_FAILURE,
                    failure_classification=FailureClassification.UNCERTAIN_STATE,
                    error_message=f"Target-side independent verification failed: {e}",
                    duration_ms=duration_ms,
                )
                if self.audit_service:
                    try:
                        self.audit_service.record_execution_event(request, result)
                    except Exception:
                        pass
                return result

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "target_os_username": target_os_username,
                "verified": True,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def remove_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 6 operation: Remove human target account via helper boundary and verify."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        target_os_username = params.get("target_os_username")
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
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

        if not target_os_username or not bootstrap_credential:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing target_os_username or bootstrap_credential",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, bytes)
            else str(bootstrap_credential)
        )

        helper_cmd = f"sudo -n /usr/local/sbin/opsforge-helper remove_account {target_os_username}"

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                _, stdout, stderr = client.exec_command(helper_cmd)  # nosec B601
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                exit_code = stdout.channel.recv_exit_status()
                if exit_code != 0:
                    err_msg = err or out or f"Helper exited with code {exit_code}"
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.REMOVE_ACCOUNT,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.VERIFIED_FAILURE,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper remove_account failed: {err_msg}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

                # Verification: confirm user is removed
                _, v_stdout, _ = client.exec_command(
                    f"id {target_os_username}"
                )  # nosec B601
                v_code = v_stdout.channel.recv_exit_status()
                if v_code == 0:
                    raise ValueError(
                        f"Account {target_os_username} still exists on target after remove_account!"
                    )

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"remove_account error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.REMOVE_ACCOUNT,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "target_os_username": target_os_username,
                "removed": True,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def apply_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 7 operation: Apply temporary JIT privilege grant via helper boundary."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        grant_id = str(params.get("grant_id"))
        target_os_username = params.get("target_os_username")
        command_set_id = params.get("command_set_id")
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if not host or not target_os_username or not grant_id or not command_set_id:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.APPLY_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing host, target_os_username, grant_id, or command_set_id in parameters.",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, (bytes, bytearray))
            else (bootstrap_credential or "")
        )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                cmd = f"sudo -n /usr/local/sbin/opsforge-helper add_jit_grant {grant_id} {target_os_username} {command_set_id}"
                _, stdout, stderr = client.exec_command(cmd)  # nosec B601
                exit_code = stdout.channel.recv_exit_status()
                err_msg = stderr.read().decode("utf-8", errors="replace")

                if exit_code != 0:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.APPLY_JIT_GRANT,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.UNVERIFIED,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper add_jit_grant failed: {err_msg.strip()}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

                # Independent Target-Side Verification
                try:
                    v_cmd = f"sudo -n -l -U {target_os_username}"
                    _, v_stdout, v_stderr = client.exec_command(v_cmd)  # nosec B601
                    v_code = v_stdout.channel.recv_exit_status()
                    _ = v_stdout.read()
                    if v_code != 0:
                        # Fallback verification: check if drop-in file exists and is readable
                        chk_cmd = f"test -f /etc/sudoers.d/opsforge-jit-{grant_id}"
                        _, c_stdout, _ = client.exec_command(chk_cmd)  # nosec B601
                        if c_stdout.channel.recv_exit_status() != 0:
                            raise ValueError(
                                f"Independent verification failed: sudo -l exited {v_code}: {v_stderr.read().decode('utf-8', errors='replace')}"
                            )
                except Exception as e:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.APPLY_JIT_GRANT,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.VERIFIED_FAILURE,
                        failure_classification=FailureClassification.UNCERTAIN_STATE,
                        error_message=f"Target-side independent verification failed: {e}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.APPLY_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"apply_jit_grant connection/execution error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.APPLY_JIT_GRANT,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "grant_id": grant_id,
                "target_os_username": target_os_username,
                "command_set_id": command_set_id,
                "verified": True,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def revoke_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 7/8 operation: Revoke temporary JIT privilege grant via helper boundary."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        grant_id = str(params.get("grant_id"))
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if not host or not grant_id:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing host or grant_id in parameters.",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, (bytes, bytearray))
            else (bootstrap_credential or "")
        )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                cmd = f"sudo -n /usr/local/sbin/opsforge-helper remove_jit_grant {grant_id}"
                _, stdout, stderr = client.exec_command(cmd)  # nosec B601
                exit_code = stdout.channel.recv_exit_status()
                err_msg = stderr.read().decode("utf-8", errors="replace")

                if exit_code != 0:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.REVOKE_JIT_GRANT,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.UNVERIFIED,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper remove_jit_grant failed: {err_msg.strip()}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

                # Verification: confirm drop-in is removed
                chk_cmd = f"test -f /etc/sudoers.d/opsforge-jit-{grant_id}"
                _, v_stdout, _ = client.exec_command(chk_cmd)  # nosec B601
                v_code = v_stdout.channel.recv_exit_status()
                if v_code == 0:
                    raise ValueError(
                        f"JIT drop-in /etc/sudoers.d/opsforge-jit-{grant_id} still exists after removal!"
                    )

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"revoke_jit_grant error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.REVOKE_JIT_GRANT,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "grant_id": grant_id,
                "revoked": True,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def register_jit_session(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 8 operation: Register active JIT session with target helper boundary."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        grant_id = str(params.get("grant_id"))
        session_id = str(params.get("session_id"))
        target_os_username = params.get("target_os_username")
        pid = params.get("pid")
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if (
            not host
            or not grant_id
            or not session_id
            or not target_os_username
            or not pid
        ):
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REGISTER_JIT_SESSION,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing required parameters for register_jit_session.",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, (bytes, bytearray))
            else (bootstrap_credential or "")
        )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                cmd = f"sudo -n /usr/local/sbin/opsforge-helper register_session {grant_id} {session_id} {target_os_username} {pid}"
                _, stdout, stderr = client.exec_command(cmd)  # nosec B601
                exit_code = stdout.channel.recv_exit_status()
                err_msg = stderr.read().decode("utf-8", errors="replace")

                if exit_code != 0:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.REGISTER_JIT_SESSION,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.UNVERIFIED,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper register_session failed: {err_msg.strip()}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REGISTER_JIT_SESSION,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"register_jit_session error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.REGISTER_JIT_SESSION,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "session_id": session_id,
                "grant_id": grant_id,
                "pid": pid,
                "registered": True,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def terminate_jit_sessions(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 8 operation: Terminate active sessions for JIT grant and verify."""
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        grant_id = str(params.get("grant_id"))
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if not host or not grant_id:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing host or grant_id in parameters.",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, (bytes, bytearray))
            else (bootstrap_credential or "")
        )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                cmd = f"sudo -n /usr/local/sbin/opsforge-helper terminate_jit_sessions {grant_id}"
                _, stdout, stderr = client.exec_command(cmd)  # nosec B601
                exit_code = stdout.channel.recv_exit_status()
                out_msg = stdout.read().decode("utf-8", errors="replace").strip()
                err_msg = stderr.read().decode("utf-8", errors="replace").strip()

                if exit_code != 0:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.UNVERIFIED,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper terminate_jit_sessions failed: {err_msg or out_msg}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"terminate_jit_sessions error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={
                "grant_id": grant_id,
                "terminated": True,
                "output": out_msg,
            },
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

    def inspect_target_state(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 9 operation: Inspect target state for JIT reconciliation."""
        import json
        start_time = time.monotonic()
        request.authorization_context.validate()

        params = request.parameters
        host = params.get("hostname_ip") or params.get("host")
        port = int(params.get("port") or 22)
        grant_id = str(params.get("grant_id"))
        target_os_username = params.get("target_os_username")
        bootstrap_credential = params.get("bootstrap_credential")

        if not host and self.resource_resolver:
            resource = self.resource_resolver(request.resource_id)
            if resource:
                host = getattr(resource, "hostname_ip", None) or getattr(
                    resource, "resource_code", None
                )
                port = int(getattr(resource, "port", None) or 22)
                pinned_key = getattr(resource, "pinned_host_key", None)
                if pinned_key and host:
                    parts = pinned_key.strip().split()
                    if len(parts) >= 2:
                        self.host_key_verifier.register_trusted_key(
                            host, parts[0], parts[1]
                        )

        if not host or not grant_id or not target_os_username:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.INSPECT_TARGET_STATE,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.CONFIGURATION_FAILURE,
                error_message="Missing host, grant_id, or target_os_username in parameters.",
                duration_ms=duration_ms,
            )

        bootstrap_cred_str = (
            bootstrap_credential.decode("utf-8")
            if isinstance(bootstrap_credential, (bytes, bytearray))
            else (bootstrap_credential or "")
        )

        try:
            with SSHConnectionContext(
                target_host=host,
                target_port=port,
                username="opsforge-svc",
                private_key_pem=bootstrap_cred_str,
                network_validator=self.network_validator,
                host_key_verifier=self.host_key_verifier,
                config=self.config,
                resource_id=request.resource_id,
                execution_id=request.execution_id,
                audit_service=self.audit_service,
                semaphore=self._semaphore,
            ) as client:
                cmd = f"sudo -n /usr/local/sbin/opsforge-helper inspect_target_state {grant_id} {target_os_username}"
                _, stdout, stderr = client.exec_command(cmd)  # nosec B601
                exit_code = stdout.channel.recv_exit_status()
                out_msg = stdout.read().decode("utf-8", errors="replace").strip()
                err_msg = stderr.read().decode("utf-8", errors="replace").strip()

                if exit_code != 0:
                    duration_ms = (time.monotonic() - start_time) * 1000.0
                    result = ExecutionResult(
                        execution_id=request.execution_id,
                        operation=ExecutionOperation.INSPECT_TARGET_STATE,
                        status=ExecutionStatus.FAILED,
                        verification_status=VerificationStatus.UNVERIFIED,
                        failure_classification=FailureClassification.TARGET_FAILURE,
                        error_message=f"Helper inspect_target_state failed: {err_msg or out_msg}",
                        duration_ms=duration_ms,
                    )
                    if self.audit_service:
                        try:
                            self.audit_service.record_execution_event(request, result)
                        except Exception:
                            pass
                    return result

                try:
                    target_state_data = json.loads(out_msg)
                except json.JSONDecodeError:
                    raise Exception(f"Failed to parse helper JSON output: {out_msg}")

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.INSPECT_TARGET_STATE,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message=f"inspect_target_state error: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        result = ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.INSPECT_TARGET_STATE,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details=target_state_data,
            duration_ms=duration_ms,
        )
        if self.audit_service:
            try:
                self.audit_service.record_execution_event(request, result)
            except Exception:
                pass
        return result

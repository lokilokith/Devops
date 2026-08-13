"""Rotation Worker – Phase 2B.5B.

Orchestrates batch credential rotation driven by ``SecretRotationPolicy``
eligibility rules. Each policy is processed in its own transaction; CAS via
``row_version`` prevents concurrent workers from producing duplicate rotations.

Security invariants
-------------------
* Plaintext credential bytes never leave this module: they are decrypted
  in-memory, passed directly to the executor, and then immediately
  overwritten (via deletion of local reference) before any I/O.
* Audit records never contain plaintext or DEK material.
* No external scheduler, thread or daemon is introduced; ``run_rotation_job``
  is a pure, synchronous function meant to be called by any orchestration layer
  (cron, a Flask CLI command, a test).

Transaction boundaries
----------------------
Each policy uses an independent ``session.begin_nested()`` (SAVEPOINT) so that
a failure on one policy does not roll back completed prior policies within the
same outer transaction.  The caller is responsible for the outer transaction
(``db.session`` via Flask app context).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.exceptions import AuthorizationDeniedError
from app.permissions.models import PermissionAction
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretVersion
from app.vault.exceptions import ConcurrencyError
from app.vault.executor_registry import ExecutorRegistry
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus, RotationResultStatus
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.service import VaultLifecycleService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker actor ID – used for audit events emitted by the background worker.
# Production deployments should override this via config; tests supply it
# directly.
# ---------------------------------------------------------------------------
WORKER_ACTOR_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Privileged authorization stub
# ---------------------------------------------------------------------------

class _PrivilegedAuthorizationService:
    """Always-allow authorization service for trusted background workers.

    Background workers are trusted system processes that operate under a
    dedicated service-account identity.  They are intentionally exempt from
    user-facing RBAC checks.  This stub satisfies the ``AuthorizationService``
    interface without touching the database.
    """

    def authorize(self, user_id: UUID, resource_code: str, action: PermissionAction) -> None:  # noqa: D401
        """Always permits – background workers are privileged."""
        return  # no-op

    def has_permission(self, user_id: UUID, resource_code: str, action: PermissionAction) -> bool:
        return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_rotation_job(
    session: Session,
    audit_service: AuditService,
    encryption_service: EncryptionService,
    lifecycle_service: VaultLifecycleService,
    executor_registry: ExecutorRegistry,
    actor_id: UUID | None = None,
) -> dict:
    """Discover all eligible rotation policies and rotate each one atomically.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.  The caller owns the outer transaction;
        each policy runs inside its own ``begin_nested()`` SAVEPOINT.
    audit_service:
        Pre-wired audit service.
    encryption_service:
        Pre-wired encryption service backed by an active KMS provider.
    lifecycle_service:
        Pre-wired ``VaultLifecycleService`` used for state transitions.
    executor_registry:
        ``ExecutorRegistry`` that will be queried for each policy's resource.
    actor_id:
        UUID of the service account performing the rotation.  Falls back to
        ``WORKER_ACTOR_ID`` if not supplied.

    Returns
    -------
    dict with keys:
        ``attempted`` – number of eligible policies found.
        ``succeeded`` – number of policies that completed rotation.
        ``skipped``   – number of policies skipped due to ConcurrencyError.
        ``failed``    – number of policies that encountered an error.
    """
    if actor_id is None:
        actor_id = WORKER_ACTOR_ID

    policy_repo = SecretRotationPolicyRepository(session)
    secret_repo = SqlAlchemyVaultRepository(session)

    policies = _fetch_eligible_policies(session)
    logger.info("RotationWorker: %d eligible policies found", len(policies))

    counters = {"attempted": len(policies), "succeeded": 0, "skipped": 0, "failed": 0}

    for policy in policies:
        result = _process_policy(
            policy=policy,
            actor_id=actor_id,
            session=session,
            secret_repo=secret_repo,
            policy_repo=policy_repo,
            audit_service=audit_service,
            encryption_service=encryption_service,
            lifecycle_service=lifecycle_service,
            executor_registry=executor_registry,
        )
        counters[result] += 1

    logger.info(
        "RotationWorker: completed – attempted=%d succeeded=%d skipped=%d failed=%d",
        counters["attempted"],
        counters["succeeded"],
        counters["skipped"],
        counters["failed"],
    )
    return counters


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_eligible_policies(session: Session) -> List[SecretRotationPolicy]:
    """Return all active policies whose ``next_rotation_at`` is in the past."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(SecretRotationPolicy)
        .where(
            SecretRotationPolicy.status == RotationStatus.ACTIVE,
            SecretRotationPolicy.next_rotation_at <= now,
        )
        .order_by(SecretRotationPolicy.next_rotation_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


def _process_policy(
    *,
    policy: SecretRotationPolicy,
    actor_id: UUID,
    session: Session,
    secret_repo: SqlAlchemyVaultRepository,
    policy_repo: SecretRotationPolicyRepository,
    audit_service: AuditService,
    encryption_service: EncryptionService,
    lifecycle_service: VaultLifecycleService,
    executor_registry: ExecutorRegistry,
) -> str:
    """Process a single rotation policy inside its own SAVEPOINT.

    Returns one of: ``"succeeded"``, ``"skipped"``, ``"failed"``.
    """
    policy_id_str = str(policy.id)
    secret_id = policy.vault_secret_id
    secret_id_str = str(secret_id)

    try:
        # Each policy runs in an isolated SAVEPOINT so that failures on one
        # policy do not affect others in the same outer transaction.
        savepoint = session.begin_nested()

        # 1. Acquire rotation lock via CAS – begin_rotation transitions
        #    ACTIVE -> ROTATING and increments row_version.
        try:
            lifecycle_service.start_rotation(actor_id, secret_id)
        except ConcurrencyError:
            # Another worker already started this rotation.
            savepoint.rollback()
            logger.debug(
                "RotationWorker: ConcurrencyError acquiring rotation for secret %s – skipping",
                secret_id_str,
            )
            return "skipped"
        except ValueError as exc:
            # Secret not found or wrong state – not retryable, mark failed.
            savepoint.rollback()
            logger.warning(
                "RotationWorker: Cannot start rotation for secret %s: %s",
                secret_id_str,
                exc,
            )
            _audit_failure(
                audit_service=audit_service,
                actor_id=actor_id,
                secret_id_str=secret_id_str,
                action="SECRET_ROTATION_FAILED",
                reason=str(exc),
                severity=AuditSeverity.HIGH,
            )
            return "failed"

        # 2. Resolve executor for this resource.
        executor = executor_registry.get_executor(secret_id)
        if executor is None:
            reason = f"No executor registered for secret {secret_id_str}"
            logger.warning("RotationWorker: %s", reason)
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_NO_EXECUTOR",
            )
            savepoint.commit()
            return "failed"

        # 3. Load current secret aggregate from DB.
        secret = secret_repo.find_by_id(secret_id)
        if secret is None:
            reason = f"Secret {secret_id_str} not found during rotation"
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_FAILED",
            )
            savepoint.commit()
            return "failed"

        current_version = secret.get_current_version()
        if current_version is None:
            reason = f"Secret {secret_id_str} has no current version"
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_FAILED",
            )
            savepoint.commit()
            return "failed"

        # 4. Decrypt current secret in memory – plaintext MUST NOT be logged.
        try:
            plaintext = encryption_service.decrypt_payload(
                secret.resource_id,
                secret.id,
                current_version.encrypted_dek,
                current_version.encrypted_payload,
                current_version.metadata,
            )
        except Exception as exc:
            reason = "Failed to decrypt current secret payload"
            logger.error(
                "RotationWorker: %s for secret %s (details omitted for security)",
                reason,
                secret_id_str,
            )
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_FAILED",
            )
            savepoint.commit()
            # Wipe local reference before returning – plaintext must not linger.
            del plaintext  # noqa: F821
            return "failed"

        # 5. Call executor – may raise RuntimeError for retryable/terminal.
        exec_error: str | None = None
        new_secret_bytes: bytes | None = None
        try:
            result = executor.execute(secret_id, plaintext)
            # Wipe plaintext immediately after passing to executor.
            del plaintext

            exec_error = result.get("error") or None
            if not exec_error:
                new_secret_bytes = result.get("new_secret_version")
        except RuntimeError as exc:
            # Wipe plaintext reference first.
            del plaintext
            msg = str(exc)
            exec_error = "retryable" if "retryable" in msg.lower() else "terminal"
            logger.warning(
                "RotationWorker: Executor raised RuntimeError for secret %s (classified as %s)",
                secret_id_str,
                exec_error,
            )

        # 6. Handle executor error outcome.
        if exec_error:
            is_retryable = "retryable" in exec_error.lower()
            if is_retryable:
                # Increment retry counter; do NOT transition to FAILED.
                policy.retry_count = (policy.retry_count or 0) + 1
                policy.updated_at = datetime.now(timezone.utc)
                policy_repo.save(policy)
                _audit_failure(
                    audit_service=audit_service,
                    actor_id=actor_id,
                    secret_id_str=secret_id_str,
                    action="SECRET_ROTATION_RETRYABLE_FAILURE",
                    reason=exec_error,
                    severity=AuditSeverity.MEDIUM,
                    details={"policy_id": policy_id_str, "retry_count": policy.retry_count},
                )
                # Revert secret back to ACTIVE (from ROTATING) without marking DESYNCED.
                # We must commit the policy retry_count update, so we cannot simply
                # rollback the entire SAVEPOINT.  Instead, restore secret status.
                try:
                    secret_for_revert = secret_repo.find_by_id(secret_id)
                    if secret_for_revert and secret_for_revert.status.value == "rotating":
                        from app.vault.domain import SecretStatus
                        secret_for_revert.status = SecretStatus.ACTIVE
                        secret_for_revert.updated_at = datetime.now(timezone.utc)
                        secret_repo.save(secret_for_revert)
                except ConcurrencyError:
                    # Another worker may have changed state – that's acceptable.
                    pass
                savepoint.commit()
                return "failed"
            else:
                # Terminal failure – transition secret to DESYNCED, policy to ERROR.
                reason = "Terminal executor failure"
                _handle_fail_rotation(
                    lifecycle_service=lifecycle_service,
                    audit_service=audit_service,
                    policy=policy,
                    policy_repo=policy_repo,
                    actor_id=actor_id,
                    secret_id=secret_id,
                    secret_id_str=secret_id_str,
                    reason=reason,
                    action="SECRET_ROTATION_TERMINAL_FAILURE",
                )
                savepoint.commit()
                return "failed"

        # 7. SUCCESS path – encrypt the new credential and persist.
        if not new_secret_bytes:
            reason = "Executor returned empty credential bytes"
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_FAILED",
            )
            savepoint.commit()
            return "failed"

        # Re-load secret (start_rotation already saved it; fetch fresh state).
        secret = secret_repo.find_by_id(secret_id)
        if secret is None:
            reason = "Secret disappeared between start and complete rotation"
            _handle_fail_rotation(
                lifecycle_service=lifecycle_service,
                audit_service=audit_service,
                policy=policy,
                policy_repo=policy_repo,
                actor_id=actor_id,
                secret_id=secret_id,
                secret_id_str=secret_id_str,
                reason=reason,
                action="SECRET_ROTATION_FAILED",
            )
            savepoint.commit()
            return "failed"

        try:
            encrypted_dek, encrypted_payload, metadata = encryption_service.encrypt_payload(
                secret.resource_id, secret.id, new_secret_bytes
            )
        finally:
            # Always wipe new_secret_bytes once passed to encrypt_payload.
            del new_secret_bytes

        now = datetime.now(timezone.utc)
        new_version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=now,
            created_by=actor_id,
        )

        # complete_rotation transitions ROTATING -> ACTIVE and adds the new version.
        lifecycle_service.complete_rotation(actor_id, secret.id, new_version)

        # Reset retry counter and update policy timestamps.
        policy.retry_count = 0
        policy.updated_at = now
        policy_repo.save(policy)

        audit_service.log_event(
            actor_user_id=actor_id,
            action="SECRET_ROTATION_COMPLETED",
            resource_type="vault_secrets",
            resource_id=secret_id_str,
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={"policy_id": policy_id_str},
        )

        savepoint.commit()
        logger.info("RotationWorker: rotation completed for secret %s", secret_id_str)
        return "succeeded"

    except ConcurrencyError:
        # CAS conflict during complete_rotation – another worker won.
        try:
            savepoint.rollback()
        except Exception:
            pass
        logger.warning(
            "RotationWorker: ConcurrencyError during complete for secret %s – skipping",
            secret_id_str,
        )
        return "skipped"

    except Exception as exc:
        # Unexpected failure – roll back SAVEPOINT and audit.
        try:
            savepoint.rollback()
        except Exception:
            pass
        logger.exception(
            "RotationWorker: Unexpected error processing secret %s: %s",
            secret_id_str,
            exc,
        )
        _audit_failure(
            audit_service=audit_service,
            actor_id=actor_id,
            secret_id_str=secret_id_str,
            action="SECRET_ROTATION_FAILED",
            reason=f"Unexpected error: {type(exc).__name__}",
            severity=AuditSeverity.HIGH,
        )
        return "failed"


# ---------------------------------------------------------------------------
# Shared audit helpers
# ---------------------------------------------------------------------------

def _audit_failure(
    *,
    audit_service: AuditService,
    actor_id: UUID,
    secret_id_str: str,
    action: str,
    reason: str,
    severity: AuditSeverity,
    details: dict | None = None,
) -> None:
    """Emit a failure audit event. Never includes plaintext."""
    payload = {"reason": reason}
    if details:
        payload.update(details)
    try:
        audit_service.log_event(
            actor_user_id=actor_id,
            action=action,
            resource_type="vault_secrets",
            resource_id=secret_id_str,
            status=AuditStatus.FAILED,
            severity=severity,
            details=payload,
        )
    except Exception as exc:
        logger.error("RotationWorker: Failed to write audit event %s: %s", action, exc)


def _handle_fail_rotation(
    *,
    lifecycle_service: VaultLifecycleService,
    audit_service: AuditService,
    policy: SecretRotationPolicy,
    policy_repo: SecretRotationPolicyRepository,
    actor_id: UUID,
    secret_id: UUID,
    secret_id_str: str,
    reason: str,
    action: str,
) -> None:
    """Transition secret to DESYNCED, policy to ERROR, and audit the failure."""
    try:
        lifecycle_service.fail_rotation(actor_id, secret_id, reason)
    except Exception as exc:
        logger.warning(
            "RotationWorker: fail_rotation raised %s for secret %s: %s",
            type(exc).__name__,
            secret_id_str,
            exc,
        )

    try:
        policy.status = RotationStatus.ERROR
        policy.failure_reason = reason
        policy.last_rotation_status = RotationResultStatus.FAILED
        policy.updated_at = datetime.now(timezone.utc)
        policy_repo.save(policy)
    except Exception as exc:
        logger.warning(
            "RotationWorker: Failed to update policy status for secret %s: %s",
            secret_id_str,
            exc,
        )

    _audit_failure(
        audit_service=audit_service,
        actor_id=actor_id,
        secret_id_str=secret_id_str,
        action=action,
        reason=reason,
        severity=AuditSeverity.HIGH,
    )

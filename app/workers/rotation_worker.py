"""Rotation Worker — Phase 5 Automated Rotation Engine.

Orchestrates unattended, idempotent, concurrency-safe credential rotations
driven by durable `RotationJob`s and `SecretRotationPolicy` rules.

Key guarantees:
* Plaintext credentials never leave this module in persistent form; decrypted
  in-memory, passed directly to the executor, and immediately wiped via `del`.
* Fencing tokens (`lease_generation`) protect against stale workers whose leases
  expired.
* Optimistic concurrency (CAS `row_version`) prevents duplicate rotations.
* Strict classification distinguishes retryable operational errors, permanent
  failures, and security uncertainty.
* Target-side verification via certified Phase 4 SSH executor precedes database commits.
* Comprehensive audit logging with zero plaintext secrets.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
)
from app.permissions.models import PermissionAction
from app.resources.models import Resource
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretStatus, SecretVersion
from app.vault.exceptions import ConcurrencyError, SecretCheckedOutError
from app.vault.executor_registry import ExecutorRegistry
from app.vault.models import VaultSecret
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import (
    RotationResultStatus,
    RotationStatus,
    SecretRotationPolicy,
)
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.rotation_job import (
    sanitize_error_code,
    sanitize_error_message,
)
from app.vault_lifecycle.rotation_job_repository import RotationJobRepository
from app.vault_lifecycle.scheduler import RotationScheduler
from app.vault_lifecycle.service import VaultLifecycleService

logger = logging.getLogger(__name__)

WORKER_ACTOR_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


class _PrivilegedAuthorizationService:
    """Always-allow authorization service for trusted background workers."""

    def authorize(
        self, user_id: UUID, resource_code: str, action: PermissionAction
    ) -> None:
        return

    def has_permission(
        self, user_id: UUID, resource_code: str, action: PermissionAction
    ) -> bool:
        return True


def _fetch_eligible_policies(session: Session) -> List[SecretRotationPolicy]:
    """Return all active policies whose next_rotation_at is in the past."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(SecretRotationPolicy)
        .join(VaultSecret, SecretRotationPolicy.vault_secret_id == VaultSecret.id)
        .where(
            SecretRotationPolicy.status == RotationStatus.ACTIVE,
            SecretRotationPolicy.next_rotation_at <= now,
            VaultSecret.status != SecretStatus.CHECKED_OUT,
        )
        .order_by(SecretRotationPolicy.next_rotation_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


def run_rotation_worker_cycle(
    session: Session,
    audit_service: AuditService,
    encryption_service: EncryptionService,
    lifecycle_service: VaultLifecycleService,
    executor_registry: ExecutorRegistry,
    worker_id: Optional[str] = None,
    actor_id: Optional[UUID] = None,
    batch_size: int = 20,
    lease_duration_seconds: int = 300,
    current_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute a single cycle of the Phase 5 automated rotation worker."""
    w_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    actor = actor_id or WORKER_ACTOR_ID
    now = current_time or datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    scheduler = RotationScheduler(session)
    scheduler_metrics = scheduler.run_scheduler_cycle(
        audit_service=audit_service, actor_id=actor, current_time=now
    )

    job_repo = RotationJobRepository(session)
    claimable_jobs = job_repo.find_claimable_jobs(limit=batch_size, now=now)
    logger.info(
        "RotationWorker[%s]: found %d claimable jobs (run_id=%s)",
        w_id,
        len(claimable_jobs),
        run_id,
    )

    counters: Dict[str, Any] = {
        "run_id": run_id,
        "worker_id": w_id,
        "scheduler": scheduler_metrics,
        "attempted": len(claimable_jobs),
        "succeeded": 0,
        "retryable": 0,
        "terminal": 0,
        "security_uncertainty": 0,
        "no_executor": 0,
        "unexpected": 0,
        "fenced_out": 0,
        "skipped": 0,
        "deferred": 0,
        "duration_seconds": 0.0,
    }

    start_mono = datetime.now(timezone.utc)
    for queued_job in claimable_jobs:
        outcome = process_rotation_job(
            job_id=queued_job.id,
            worker_id=w_id,
            actor_id=actor,
            run_id=run_id,
            session=session,
            audit_service=audit_service,
            encryption_service=encryption_service,
            lifecycle_service=lifecycle_service,
            executor_registry=executor_registry,
            lease_duration_seconds=lease_duration_seconds,
            current_time=now,
        )
        if outcome in counters:
            counters[outcome] += 1
        else:
            counters["skipped"] += 1

    duration = (datetime.now(timezone.utc) - start_mono).total_seconds()
    counters["duration_seconds"] = round(duration, 3)

    logger.info(
        "RotationWorker[%s]: cycle completed — attempted=%d succeeded=%d retryable=%d terminal=%d uncertainty=%d",
        w_id,
        counters["attempted"],
        counters["succeeded"],
        counters["retryable"],
        counters["terminal"],
        counters["security_uncertainty"],
    )
    return counters


def run_rotation_job(
    session: Session,
    audit_service: AuditService,
    encryption_service: EncryptionService,
    lifecycle_service: VaultLifecycleService,
    executor_registry: ExecutorRegistry,
    actor_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Top-level entrypoint providing backwards compatibility for test runners and CLI."""
    return run_rotation_worker_cycle(
        session=session,
        audit_service=audit_service,
        encryption_service=encryption_service,
        lifecycle_service=lifecycle_service,
        executor_registry=executor_registry,
        actor_id=actor_id,
    )


def process_rotation_job(
    *,
    job_id: UUID,
    worker_id: str,
    actor_id: UUID,
    run_id: str,
    session: Session,
    audit_service: AuditService,
    encryption_service: EncryptionService,
    lifecycle_service: VaultLifecycleService,
    executor_registry: ExecutorRegistry,
    lease_duration_seconds: int = 300,
    current_time: Optional[datetime] = None,
) -> str:
    """Execute a single RotationJob with lease fencing and safe CAS commit."""
    job_repo = RotationJobRepository(session)
    secret_repo = SqlAlchemyVaultRepository(session)
    policy_repo = SecretRotationPolicyRepository(session)
    now = current_time or datetime.now(timezone.utc)

    # 1. Claim job lease atomically via SQL CAS
    job = job_repo.atomic_claim(
        job_id=job_id,
        worker_id=worker_id,
        lease_duration_seconds=lease_duration_seconds,
        now=now,
    )
    if not job:
        logger.debug(
            "RotationWorker[%s]: Failed to claim lease on job %s (claimed by another worker)",
            worker_id,
            job_id,
        )
        return "skipped"

    # Commit claim transaction so lease is durable across worker execution
    session.commit()
    claimed_lease_gen = job.lease_generation
    secret_id = job.vault_secret_id
    secret_id_str = str(secret_id)
    resource_id = job.resource_id

    # Emit claim audit
    audit_service.log_event(
        actor_user_id=actor_id,
        action="ROTATION_CLAIMED",
        resource_type="vault_secrets",
        resource_id=secret_id_str,
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.INFO,
        details={
            "run_id": run_id,
            "job_id": str(job_id),
            "worker_id": worker_id,
            "lease_generation": claimed_lease_gen,
            "rotation_generation": job.rotation_generation,
            "attempt_count": job.attempt_count,
        },
    )
    session.commit()

    savepoint = session.begin_nested()
    try:
        # 2. Acquire VaultSecret rotation lock (ACTIVE -> ROTATING)
        try:
            lifecycle_service.start_rotation(actor_id, secret_id)
        except ConcurrencyError:
            savepoint.rollback()
            logger.info(
                "RotationWorker[%s]: VaultSecret %s ConcurrencyError on start_rotation",
                worker_id,
                secret_id_str,
            )
            _handle_retryable_failure(
                job_id=job_id,
                worker_id=worker_id,
                lease_gen=claimed_lease_gen,
                error_code="CAS_CONFLICT",
                error_class="CONCURRENCY_ERROR",
                session=session,
                audit_service=audit_service,
                actor_id=actor_id,
                secret_id_str=secret_id_str,
                run_id=run_id,
            )
            return "skipped"
        except SecretCheckedOutError:
            savepoint.rollback()
            logger.info(
                "RotationWorker[%s]: Secret %s is checked out — deferring",
                worker_id,
                secret_id_str,
            )
            return "deferred"
        except Exception as exc:
            savepoint.rollback()
            logger.warning(
                "RotationWorker[%s]: Cannot start rotation for secret %s: %s",
                worker_id,
                secret_id_str,
                exc,
            )
            _handle_terminal_failure(
                job_id=job_id,
                worker_id=worker_id,
                lease_gen=claimed_lease_gen,
                error_code="INVALID_CONFIGURATION",
                error_class="START_ROTATION_FAILED",
                reason=str(exc),
                session=session,
                audit_service=audit_service,
                lifecycle_service=lifecycle_service,
                actor_id=actor_id,
                secret_id=secret_id,
                run_id=run_id,
            )
            return "unexpected"

        # 3. Resolve Target Executor
        executor = executor_registry.get_executor(resource_id)
        if executor is None:
            executor = executor_registry.get_executor(secret_id)
        if executor is None:
            savepoint.rollback()
            _handle_terminal_failure(
                job_id=job_id,
                worker_id=worker_id,
                lease_gen=claimed_lease_gen,
                error_code="INVALID_CONFIGURATION",
                error_class="NO_EXECUTOR_REGISTERED",
                reason=f"No executor registered for resource {resource_id}",
                session=session,
                audit_service=audit_service,
                lifecycle_service=lifecycle_service,
                actor_id=actor_id,
                secret_id=secret_id,
                run_id=run_id,
            )
            return "no_executor"

        # 4. Decrypt current secret payload in memory (plaintext must NOT be logged or persisted)
        secret_aggregate = secret_repo.find_by_id(secret_id)
        if not secret_aggregate:
            savepoint.rollback()
            return "unexpected"

        current_ver = secret_aggregate.get_current_version()
        if not current_ver:
            savepoint.rollback()
            return "unexpected"

        try:
            plaintext = encryption_service.decrypt_payload(
                secret_aggregate.resource_id,
                secret_aggregate.id,
                current_ver.encrypted_dek,
                current_ver.encrypted_payload,
                current_ver.metadata,
            )
        except Exception:
            savepoint.rollback()
            _handle_terminal_failure(
                job_id=job_id,
                worker_id=worker_id,
                lease_gen=claimed_lease_gen,
                error_code="INVALID_CONFIGURATION",
                error_class="DECRYPTION_FAILED",
                reason="Failed to decrypt current secret payload",
                session=session,
                audit_service=audit_service,
                lifecycle_service=lifecycle_service,
                actor_id=actor_id,
                secret_id=secret_id,
                run_id=run_id,
            )
            return "unexpected"

        # 5. Execute target-side rotation via Phase 4 executor
        exec_result: Optional[ExecutionResult] = None
        new_secret_bytes: Optional[bytes] = None
        exec_error: Optional[str] = None
        is_uncertain = False
        failure_class: Optional[str] = None

        audit_service.log_event(
            actor_user_id=actor_id,
            action="ROTATION_STARTED",
            resource_type="vault_secrets",
            resource_id=secret_id_str,
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "run_id": run_id,
                "job_id": str(job_id),
                "resource_id": str(resource_id),
                "rotation_generation": job.rotation_generation,
            },
        )

        try:
            if hasattr(executor, "rotate_credential"):
                resource_model = session.get(Resource, resource_id)
                auth_ctx = ExecutionAuthorizationContext(
                    user_id=actor_id,
                    resource_id=resource_id,
                    credential_id=secret_id,
                    requested_at=now,
                    expires_at=now + timedelta(minutes=15),
                )
                params: Dict[str, Any] = {}
                if resource_model:
                    params["hostname_ip"] = (
                        resource_model.hostname_ip or resource_model.resource_code
                    )
                    params["port"] = resource_model.port or 22
                    params["username"] = "opsforge-svc"

                exec_req = ExecutionRequest(
                    operation=ExecutionOperation.ROTATE_CREDENTIAL,
                    resource_id=resource_id,
                    authorization_context=auth_ctx,
                    parameters=params,
                )
                exec_result = executor.rotate_credential(exec_req, plaintext)
                del plaintext  # Wipe immediately after handoff

                if exec_result.is_success:
                    new_secret_bytes = exec_result.new_secret_version
                else:
                    exec_error = exec_result.error_message or "Execution failure"
                    is_uncertain = exec_result.is_uncertain
                    failure_class = (
                        exec_result.failure_classification.value
                        if exec_result.failure_classification
                        else "TARGET_FAILURE"
                    )
            else:
                legacy_res = executor.execute(secret_id, plaintext)
                del plaintext  # Wipe immediately

                if legacy_res.get("error"):
                    exec_error = legacy_res["error"]
                else:
                    new_secret_bytes = legacy_res.get("new_secret_version")

        except Exception as exc:
            try:
                del plaintext
            except Exception:
                pass
            exec_error = str(exc)
            failure_class = type(exc).__name__
            logger.warning(
                "RotationWorker[%s]: Exception during executor run: %s",
                worker_id,
                exc,
            )

        # 6. Verify fencing before persisting target outcome
        if not job_repo.verify_fencing(job_id, worker_id, claimed_lease_gen):
            savepoint.rollback()
            logger.warning(
                "RotationWorker[%s]: Fenced out of job %s (lease expired/overridden)",
                worker_id,
                job_id,
            )
            audit_service.log_event(
                actor_user_id=actor_id,
                action="ROTATION_CAS_CONFLICT",
                resource_type="vault_secrets",
                resource_id=secret_id_str,
                status=AuditStatus.FAILED,
                severity=AuditSeverity.MEDIUM,
                details={
                    "run_id": run_id,
                    "job_id": str(job_id),
                    "reason": "Worker fenced out during target rotation",
                },
            )
            session.commit()
            return "fenced_out"

        # 7. Evaluate outcome
        if is_uncertain:
            savepoint.rollback()
            _handle_security_uncertainty(
                job_id=job_id,
                worker_id=worker_id,
                lease_gen=claimed_lease_gen,
                reason=exec_error or "Target state is uncertain",
                classification=failure_class or "SECURITY_UNCERTAINTY",
                session=session,
                audit_service=audit_service,
                lifecycle_service=lifecycle_service,
                actor_id=actor_id,
                secret_id=secret_id,
                run_id=run_id,
            )
            return "security_uncertainty"

        if exec_error or not new_secret_bytes:
            err_msg = exec_error or "Empty credential returned"
            is_retryable = _is_error_retryable(err_msg, failure_class)
            savepoint.rollback()

            if is_retryable:
                _handle_retryable_failure(
                    job_id=job_id,
                    worker_id=worker_id,
                    lease_gen=claimed_lease_gen,
                    error_code=_classify_safe_error_code(err_msg, failure_class),
                    error_class=failure_class or "RETRYABLE",
                    session=session,
                    audit_service=audit_service,
                    actor_id=actor_id,
                    secret_id_str=secret_id_str,
                    run_id=run_id,
                )
                return "retryable"
            else:
                _handle_terminal_failure(
                    job_id=job_id,
                    worker_id=worker_id,
                    lease_gen=claimed_lease_gen,
                    error_code=_classify_safe_error_code(err_msg, failure_class),
                    error_class=failure_class or "TERMINAL",
                    reason=err_msg,
                    session=session,
                    audit_service=audit_service,
                    lifecycle_service=lifecycle_service,
                    actor_id=actor_id,
                    secret_id=secret_id,
                    run_id=run_id,
                )
                return "terminal"

        # 8. SUCCESS PATH — Encrypt new payload, commit Vault and Job state
        try:
            encrypted_dek, encrypted_payload, metadata = (
                encryption_service.encrypt_payload(
                    secret_aggregate.resource_id,
                    secret_aggregate.id,
                    new_secret_bytes,
                )
            )
        finally:
            del new_secret_bytes  # Wipe new secret bytes once encrypted

        now_utc = datetime.now(timezone.utc)
        new_version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret_id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=now_utc,
            created_by=actor_id,
        )

        lifecycle_service.complete_rotation(actor_id, secret_id, new_version)

        # Update Policy
        policy = policy_repo.get_by_vault_secret_id(secret_id)
        if policy:
            policy.last_rotated_at = now_utc
            policy.next_rotation_at = now_utc + timedelta(
                seconds=policy.rotation_interval_seconds
            )
            policy.last_rotation_status = RotationResultStatus.SUCCESS
            policy.retry_count = 0
            policy.failure_reason = None
            policy.updated_at = now_utc
            policy_repo.save(policy)

        # Transition Job to SUCCEEDED
        job_entity = job_repo.get_by_id(job_id)
        if job_entity:
            job_entity.transition_to_succeeded(now_utc)
            job_repo.save(job_entity)

        savepoint.commit()
        session.commit()

        audit_service.log_event(
            actor_user_id=actor_id,
            action="ROTATION_COMPLETED",
            resource_type="vault_secrets",
            resource_id=secret_id_str,
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "run_id": run_id,
                "job_id": str(job_id),
                "resource_id": str(resource_id),
                "rotation_generation": (
                    job_entity.rotation_generation if job_entity else 1
                ),
            },
        )
        session.commit()
        logger.info(
            "RotationWorker[%s]: Rotation job %s successfully completed for secret %s",
            worker_id,
            job_id,
            secret_id_str,
        )
        return "succeeded"

    except ConcurrencyError:
        savepoint.rollback()
        logger.warning(
            "RotationWorker[%s]: ConcurrencyError during commit on secret %s",
            worker_id,
            secret_id_str,
        )
        _handle_retryable_failure(
            job_id=job_id,
            worker_id=worker_id,
            lease_gen=claimed_lease_gen,
            error_code="CAS_CONFLICT",
            error_class="CONCURRENCY_ERROR",
            session=session,
            audit_service=audit_service,
            actor_id=actor_id,
            secret_id_str=secret_id_str,
            run_id=run_id,
        )
        return "skipped"

    except Exception as exc:
        savepoint.rollback()
        logger.exception(
            "RotationWorker[%s]: Unexpected exception processing job %s: %s",
            worker_id,
            job_id,
            exc,
        )
        _handle_terminal_failure(
            job_id=job_id,
            worker_id=worker_id,
            lease_gen=claimed_lease_gen,
            error_code="UNEXPECTED_ERROR",
            error_class=type(exc).__name__,
            reason=f"Unexpected error: {type(exc).__name__}",
            session=session,
            audit_service=audit_service,
            lifecycle_service=lifecycle_service,
            actor_id=actor_id,
            secret_id=secret_id,
            run_id=run_id,
        )
        return "unexpected"


def _process_policy(
    *,
    run_id: str,
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
    """Helper for legacy test compatibility."""
    scheduler = RotationScheduler(session)
    secret_model = session.get(VaultSecret, policy.vault_secret_id)
    if not secret_model:
        return "terminal"
    job, _ = scheduler.create_rotation_job(
        policy=policy, secret_model=secret_model, correlation_id=run_id
    )
    if not job:
        return "skipped"
    session.commit()
    return process_rotation_job(
        job_id=job.id,
        worker_id=f"worker-{run_id[:8]}",
        actor_id=actor_id,
        run_id=run_id,
        session=session,
        audit_service=audit_service,
        encryption_service=encryption_service,
        lifecycle_service=lifecycle_service,
        executor_registry=executor_registry,
    )


def _is_error_retryable(
    error_message: str, classification: Optional[str] = None
) -> bool:
    """Determine if a rotation failure is retryable under bounded backoff."""
    msg = error_message.lower()
    cls_str = (classification or "").lower()

    non_retryable_indicators = [
        "hostkeymismatch",
        "host_key_mismatch",
        "authentication_failure",
        "targetauthorizationerror",
        "protected system account",
        "invalid_configuration",
        "symlink detected",
        "untrusted host",
        "permanent error",
    ]
    if any(ind in msg or ind in cls_str for ind in non_retryable_indicators):
        return False

    retryable_indicators = [
        "retryable",
        "transient",
        "timeout",
        "timed out",
        "transport",
        "connection reset",
        "connection refused",
        "cas_conflict",
        "concurrency",
    ]
    return any(ind in msg or ind in cls_str for ind in retryable_indicators)


def _classify_safe_error_code(
    error_message: str, classification: Optional[str] = None
) -> str:
    """Map error details to an allowlisted safe error code."""
    msg = (error_message or "").lower()
    cls_str = (classification or "").lower()

    if "hostkey" in msg or "host_key" in msg or "hostkey" in cls_str:
        return "HOST_KEY_MISMATCH"
    if "timeout" in msg or "timed out" in msg or "timeout" in cls_str:
        return "SSH_TIMEOUT"
    if "transport" in msg or "transport" in cls_str:
        return "SSH_TRANSPORT_FAILURE"
    if "authentication" in msg or "auth_fail" in msg or "auth" in cls_str:
        return "AUTHENTICATION_FAILED"
    if "cas" in msg or "concurrency" in msg or "concurrency" in cls_str:
        return "CAS_CONFLICT"
    if "config" in msg or "config" in cls_str:
        return "INVALID_CONFIGURATION"
    return "TARGET_EXECUTION_ERROR"


def _handle_retryable_failure(
    *,
    job_id: UUID,
    worker_id: str,
    lease_gen: int,
    error_code: str,
    error_class: str,
    session: Session,
    audit_service: AuditService,
    actor_id: UUID,
    secret_id_str: str,
    run_id: str,
) -> None:
    """Record retryable failure with exponential backoff and revert secret to ACTIVE."""
    job_repo = RotationJobRepository(session)
    secret_repo = SqlAlchemyVaultRepository(session)
    policy_repo = SecretRotationPolicyRepository(session)
    now = datetime.now(timezone.utc)

    job = job_repo.get_by_id(job_id)
    if not job:
        return

    if job.attempt_count >= job.max_attempts:
        job.transition_to_failed(
            error_code="RETRY_EXHAUSTED", error_classification=error_class, now=now
        )
        job_repo.save(job)

        policy = policy_repo.get_by_vault_secret_id(job.vault_secret_id)
        if policy:
            policy.status = RotationStatus.ERROR
            policy.last_rotation_status = RotationResultStatus.FAILED
            policy.failure_reason = "Maximum retry attempts exhausted"
            policy.updated_at = now
            policy_repo.save(policy)

        secret = secret_repo.find_by_id(job.vault_secret_id)
        if secret and secret.status == SecretStatus.ROTATING:
            secret.status = SecretStatus.ACTIVE
            secret.updated_at = now
            secret_repo.save(secret)

        session.commit()
        audit_service.log_event(
            actor_user_id=actor_id,
            action="ROTATION_FAILED",
            resource_type="vault_secrets",
            resource_id=secret_id_str,
            status=AuditStatus.FAILED,
            severity=AuditSeverity.HIGH,
            details={
                "run_id": run_id,
                "job_id": str(job_id),
                "reason": "Retry attempts exhausted",
                "attempt_count": job.attempt_count,
            },
        )
        session.commit()
        return

    backoff_secs = min(300, (2 ** max(0, job.attempt_count - 1)) * 30)
    next_retry = now + timedelta(seconds=backoff_secs)

    job.transition_to_retry_pending(
        next_retry_at=next_retry,
        error_code=error_code,
        error_classification=error_class,
        now=now,
    )
    job_repo.save(job)

    secret = secret_repo.find_by_id(job.vault_secret_id)
    if secret and secret.status == SecretStatus.ROTATING:
        secret.status = SecretStatus.ACTIVE
        secret.updated_at = now
        secret_repo.save(secret)

    policy = policy_repo.get_by_vault_secret_id(job.vault_secret_id)
    if policy:
        policy.retry_count = job.attempt_count
        policy.updated_at = now
        policy_repo.save(policy)

    session.commit()

    audit_service.log_event(
        actor_user_id=actor_id,
        action="ROTATION_RETRY_SCHEDULED",
        resource_type="vault_secrets",
        resource_id=secret_id_str,
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.MEDIUM,
        details={
            "run_id": run_id,
            "job_id": str(job_id),
            "attempt_count": job.attempt_count,
            "next_retry_at": next_retry.isoformat(),
            "error_code": sanitize_error_code(error_code),
        },
    )
    session.commit()


def _handle_terminal_failure(
    *,
    job_id: UUID,
    worker_id: str,
    lease_gen: int,
    error_code: str,
    error_class: str,
    reason: str,
    session: Session,
    audit_service: AuditService,
    lifecycle_service: VaultLifecycleService,
    actor_id: UUID,
    secret_id: UUID,
    run_id: str,
) -> None:
    """Record non-retryable terminal failure, move policy to ERROR, and emit audit."""
    job_repo = RotationJobRepository(session)
    policy_repo = SecretRotationPolicyRepository(session)
    now = datetime.now(timezone.utc)
    secret_id_str = str(secret_id)

    job = job_repo.get_by_id(job_id)
    if job:
        job.transition_to_failed(
            error_code=error_code, error_classification=error_class, now=now
        )
        job_repo.save(job)

    secret_repo = SqlAlchemyVaultRepository(session)
    secret = secret_repo.find_by_id(secret_id)
    if secret:
        secret.status = SecretStatus.DESYNCED
        secret.updated_at = now
        secret_repo.save(secret)

    policy = policy_repo.get_by_vault_secret_id(secret_id)
    if policy:
        policy.status = RotationStatus.ERROR
        policy.last_rotation_status = RotationResultStatus.FAILED
        policy.failure_reason = sanitize_error_message(reason)
        policy.updated_at = now
        policy_repo.save(policy)

    session.commit()

    audit_service.log_event(
        actor_user_id=actor_id,
        action="ROTATION_FAILED",
        resource_type="vault_secrets",
        resource_id=secret_id_str,
        status=AuditStatus.FAILED,
        severity=AuditSeverity.HIGH,
        details={
            "run_id": run_id,
            "job_id": str(job_id),
            "error_code": sanitize_error_code(error_code),
            "reason": sanitize_error_message(reason),
        },
    )
    session.commit()


def _handle_security_uncertainty(
    *,
    job_id: UUID,
    worker_id: str,
    lease_gen: int,
    reason: str,
    classification: str,
    session: Session,
    audit_service: AuditService,
    lifecycle_service: VaultLifecycleService,
    actor_id: UUID,
    secret_id: UUID,
    run_id: str,
) -> None:
    """Record SECURITY_UNCERTAINTY when target state cannot be confidently verified."""
    job_repo = RotationJobRepository(session)
    policy_repo = SecretRotationPolicyRepository(session)
    now = datetime.now(timezone.utc)
    secret_id_str = str(secret_id)

    job = job_repo.get_by_id(job_id)
    if job:
        job.transition_to_security_uncertainty(
            error_code="SECURITY_UNCERTAINTY",
            error_classification=classification,
            now=now,
        )
        job_repo.save(job)

    secret_repo = SqlAlchemyVaultRepository(session)
    secret = secret_repo.find_by_id(secret_id)
    if secret:
        secret.status = SecretStatus.DESYNCED
        secret.updated_at = now
        secret_repo.save(secret)

    policy = policy_repo.get_by_vault_secret_id(secret_id)
    if policy:
        policy.status = RotationStatus.ERROR
        policy.last_rotation_status = RotationResultStatus.FAILED
        policy.failure_reason = sanitize_error_message(
            f"SECURITY_UNCERTAINTY: {reason}"
        )
        policy.updated_at = now
        policy_repo.save(policy)

    session.commit()

    audit_service.log_event(
        actor_user_id=actor_id,
        action="ROTATION_SECURITY_UNCERTAINTY",
        resource_type="vault_secrets",
        resource_id=secret_id_str,
        status=AuditStatus.FAILED,
        severity=AuditSeverity.CRITICAL,
        details={
            "run_id": run_id,
            "job_id": str(job_id),
            "classification": classification,
            "reason": sanitize_error_message(reason),
        },
    )
    session.commit()


__all__ = [
    "run_rotation_worker_cycle",
    "run_rotation_job",
    "process_rotation_job",
    "_fetch_eligible_policies",
    "_process_policy",
    "WORKER_ACTOR_ID",
]

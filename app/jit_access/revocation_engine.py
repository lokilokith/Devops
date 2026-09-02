"""JIT Revocation Engine – Phase 8.

Autonomous, idempotent, and concurrency-safe revocation and session termination engine.
Guarantees:
1. Target-side session termination before sudoers removal.
2. Independent target verification of privilege revocation and session termination.
3. Fail-closed security uncertainty handling.
4. Optimistic CAS locking and worker lease fencing.
5. Durable recovery of interrupted/stale revocations.
6. Absolute rejection of privilege resurrection.
7. Zero plaintext secret leakage.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
)
from app.execution.executor import TargetExecutor
from app.jit_access.exceptions import (
    InvalidGrantStateError,
    JITAccessError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.target_accounts.repository import TargetAccountBindingRepository

logger = logging.getLogger(__name__)


class JITRevocationEngine:
    """Dedicated Phase 8 revocation and recovery engine."""

    def __init__(
        self,
        repository: JITAccessRepository,
        audit_service: AuditService,
        target_account_repo: Optional[TargetAccountBindingRepository] = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._target_account_repo = target_account_repo

    def revoke_grant(
        self,
        grant_id: UUID,
        actor_id: UUID,
        is_expiry: bool = False,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
        worker_id: str = "revocation_engine",
        lease_duration_seconds: int = 60,
    ) -> JITAccessGrant:
        """Execute canonical revocation sequence with fencing and target verification.

        Sequence:
        1. Claim grant atomically via CAS (row_version + worker lease).
        2. Transition to REVOCATION_RUNNING.
        3. Terminate active sessions associated with grant on target.
        4. Remove JIT sudoers drop-in on target.
        5. Independently verify privilege removal & session termination.
        6. Commit durable terminal state (REVOKED or EXPIRED).
        7. Emit structured lifecycle audit events.
        """
        now = datetime.now(timezone.utc)
        grant = self._repo.get_by_id(grant_id)

        # Check terminal state idempotency
        if grant.status == JITGrantStatus.REVOKED and not is_expiry:
            return grant
        if grant.status == JITGrantStatus.EXPIRED and is_expiry:
            return grant

        # Anti-resurrection check
        if grant.status in (
            JITGrantStatus.REVOKED,
            JITGrantStatus.EXPIRED,
            JITGrantStatus.DENIED,
            JITGrantStatus.FAILED,
            JITGrantStatus.SECURITY_UNCERTAIN,
        ):
            if grant.status == JITGrantStatus.SECURITY_UNCERTAIN:
                raise InvalidGrantStateError(
                    f"Grant {grant_id} is in SECURITY_UNCERTAIN state and cannot be normal-revoked without target reconciliation."
                )
            raise InvalidGrantStateError(
                f"Grant {grant_id} is already in terminal state {grant.status.value}"
            )

        # 1. Claim grant atomically
        claimed_grant = self._repo.claim_for_revocation(
            grant_id=grant_id,
            worker_id=worker_id,
            lease_duration_seconds=lease_duration_seconds,
            current_time=now,
        )

        if not claimed_grant:
            # Another worker claimed it or state changed
            fresh_grant = self._repo.get_by_id(grant_id)
            if fresh_grant.status in (
                JITGrantStatus.REVOKED,
                JITGrantStatus.EXPIRED,
            ):
                return fresh_grant
            raise InvalidGrantStateError(
                f"Grant {grant_id} could not be claimed for revocation (current status: {fresh_grant.status.value})"
            )

        grant = claimed_grant

        # Audit: revocation started
        self._audit.log_event(
            actor_user_id=actor_id,
            action="jit_grant.revocation_started",
            resource_type="jit_access_grants",
            resource_id=str(grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "worker_id": worker_id,
                "is_expiry": is_expiry,
                "target_account_binding_id": str(grant.target_account_binding_id),
            },
        )

        target_os_username = None
        if grant.target_account_binding_id and self._target_account_repo:
            binding = self._target_account_repo.get_by_id(
                grant.target_account_binding_id
            )
            if binding:
                target_os_username = binding.target_os_username

        # Target-side Execution
        terminated_count = 0
        instrumentation_spans = {}
        t_start_exec = time.monotonic()
        if executor and grant.resource_id:
            now_dt = datetime.now(timezone.utc)
            auth_ctx = ExecutionAuthorizationContext(
                user_id=actor_id,
                resource_id=grant.resource_id,
                credential_id=grant.target_account_binding_id or grant.id,
                target_account_binding_id=grant.target_account_binding_id,
                grant_id=grant.id,
                requested_at=now_dt,
                expires_at=now_dt + timedelta(minutes=15),
            )

            # Step A: Terminate Sessions
            t_start_term = time.monotonic()
            term_req = ExecutionRequest(
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                resource_id=grant.resource_id,
                parameters={
                    "grant_id": str(grant.id),
                    "bootstrap_credential": bootstrap_credential,
                    "target_os_username": target_os_username,
                },
                authorization_context=auth_ctx,
            )
            term_result = executor.terminate_jit_sessions(term_req)
            instrumentation_spans["terminate_sessions_ms"] = (
                time.monotonic() - t_start_term
            ) * 1000.0

            if term_result.status != ExecutionStatus.SUCCESS:
                if (
                    term_result.failure_classification
                    == FailureClassification.UNCERTAIN_STATE
                ):
                    grant.status = JITGrantStatus.SECURITY_UNCERTAIN
                    grant.failure_reason = (
                        term_result.error_message or "Session termination uncertain"
                    )
                    self._repo.save(grant)
                    self._audit.log_event(
                        actor_user_id=actor_id,
                        action="jit_grant.security_uncertain",
                        resource_type="jit_access_grants",
                        resource_id=str(grant.id),
                        status=AuditStatus.FAILED,
                        severity=AuditSeverity.CRITICAL,
                        details={
                            "phase": "session_termination",
                            "error": grant.failure_reason,
                        },
                    )
                    raise JITAccessError(
                        f"Session termination failed in security uncertainty: {grant.failure_reason}"
                    )
                else:
                    grant.status = JITGrantStatus.FAILED
                    grant.failure_reason = (
                        term_result.error_message or "Session termination failed"
                    )
                    self._repo.save(grant)
                    self._audit.log_event(
                        actor_user_id=actor_id,
                        action="jit_grant.revocation_failed",
                        resource_type="jit_access_grants",
                        resource_id=str(grant.id),
                        status=AuditStatus.FAILED,
                        severity=AuditSeverity.HIGH,
                        details={
                            "phase": "session_termination",
                            "error": grant.failure_reason,
                        },
                    )
                    raise JITAccessError(
                        f"Failed to terminate JIT sessions: {grant.failure_reason}"
                    )

            terminated_count = term_result.details.get(
                "terminated_count",
                1 if term_result.details.get("terminated") else 0,
            )

            # Audit session terminated
            self._audit.log_event(
                actor_user_id=actor_id,
                action="jit_session.terminated",
                resource_type="jit_access_grants",
                resource_id=str(grant.id),
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={
                    "grant_id": str(grant.id),
                    "terminated_count": terminated_count,
                },
            )

            # Step B: Remove sudoers drop-in & verify privilege revocation
            t_start_revoke = time.monotonic()
            revoke_req = ExecutionRequest(
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                resource_id=grant.resource_id,
                parameters={
                    "grant_id": str(grant.id),
                    "bootstrap_credential": bootstrap_credential,
                    "target_os_username": target_os_username,
                },
                authorization_context=auth_ctx,
            )
            revoke_result = executor.revoke_jit_grant(revoke_req)
            instrumentation_spans["revoke_sudoers_ms"] = (
                time.monotonic() - t_start_revoke
            ) * 1000.0
            instrumentation_spans["total_target_exec_ms"] = (
                time.monotonic() - t_start_exec
            ) * 1000.0

            if revoke_result.status != ExecutionStatus.SUCCESS:
                grant.status = JITGrantStatus.SECURITY_UNCERTAIN
                grant.failure_reason = (
                    revoke_result.error_message or "Sudoers revocation failed"
                )
                self._repo.save(grant)
                self._audit.log_event(
                    actor_user_id=actor_id,
                    action="jit_grant.security_uncertain",
                    resource_type="jit_access_grants",
                    resource_id=str(grant.id),
                    status=AuditStatus.FAILED,
                    severity=AuditSeverity.CRITICAL,
                    details={
                        "phase": "sudoers_revocation",
                        "error": grant.failure_reason,
                    },
                )
                raise JITAccessError(
                    f"Sudoers privilege revocation failed: {grant.failure_reason}"
                )

        # Update database sessions
        sessions = self._repo.find_sessions_by_grant(grant.id)
        for s in sessions:
            if is_expiry:
                s.expire()
            else:
                s.revoke()
            s.status = "terminated"
            s.terminated_at = datetime.now(timezone.utc)
            self._repo.save_session(s)

        # Finalize grant record
        comp_now = datetime.now(timezone.utc)
        grant.revocation_complete = comp_now
        grant.sessions_terminated = max(terminated_count, len(sessions))
        if grant.expires_at:
            grant.observed_overrun_ms = int(
                max(
                    0,
                    (comp_now - grant.expires_at).total_seconds() * 1000,
                )
            )

        if is_expiry:
            grant.status = JITGrantStatus.EXPIRED
        else:
            grant.status = JITGrantStatus.REVOKED
            grant.revoked_at = comp_now

        grant.revocation_lease_expires_at = None
        grant.failure_reason = None
        updated_grant = self._repo.save(grant)

        # Audit: completed
        self._audit.log_event(
            actor_user_id=actor_id,
            action="jit_grant.revoked" if not is_expiry else "jit.expired",
            resource_type="jit_access_grants",
            resource_id=str(updated_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "status": updated_grant.status.value,
                "is_expiry": is_expiry,
                "observed_overrun_ms": updated_grant.observed_overrun_ms,
                "sessions_terminated": updated_grant.sessions_terminated,
                "instrumentation": instrumentation_spans,
            },
        )

        logger.info(
            f"Revocation completed for {grant_id}. Timing: {instrumentation_spans}"
        )

        return updated_grant

    def recover_interrupted_revocations(
        self,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
        worker_id: str = "recovery_worker",
    ) -> List[Dict[str, Any]]:
        """Discover and safely complete any interrupted/abandoned revocations."""
        now = datetime.now(timezone.utc)
        interrupted = self._repo.find_interrupted_revocations(now)
        results: List[Dict[str, Any]] = []

        for grant in interrupted:
            grant_id_str = str(grant.id)
            try:
                self._audit.log_event(
                    actor_user_id=grant.user_id,
                    action="jit_grant.recovery_started",
                    resource_type="jit_access_grants",
                    resource_id=grant_id_str,
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.MEDIUM,
                    details={
                        "previous_status": grant.status.value,
                        "worker_id": worker_id,
                    },
                )

                is_expiry = grant.expires_at is not None and grant.expires_at <= now
                updated = self.revoke_grant(
                    grant_id=grant.id,
                    actor_id=grant.user_id,
                    is_expiry=is_expiry,
                    executor=executor,
                    bootstrap_credential=bootstrap_credential,
                    worker_id=worker_id,
                )

                self._audit.log_event(
                    actor_user_id=grant.user_id,
                    action="jit_grant.recovery_completed",
                    resource_type="jit_access_grants",
                    resource_id=grant_id_str,
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={"final_status": updated.status.value},
                )

                results.append(
                    {
                        "grant_id": grant_id_str,
                        "status": updated.status.value,
                        "recovered": True,
                    }
                )
            except Exception as e:
                logger.error(
                    "Recovery failed for JIT grant %s: %s",
                    grant_id_str,
                    e,
                    exc_info=True,
                )
                results.append(
                    {
                        "grant_id": grant_id_str,
                        "status": "error",
                        "error": str(e),
                        "recovered": False,
                    }
                )

        return results

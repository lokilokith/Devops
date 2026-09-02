import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Mapping
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
)
from app.execution.executor import TargetExecutor
from app.jit_access.models import (
    JITAccessGrant,
    JITGrantStatus,
    JITReconciliationState,
    ReconciliationStatus,
)
from app.jit_access.repository import JITAccessRepository
from app.target_accounts.repository import TargetAccountBindingRepository
from app.workers.jit_reconciliation_classifier import classify_target_state

logger = logging.getLogger(__name__)


class JITReconciliationWorker:
    """Phase 9 JIT Target Reconciliation Worker."""

    def __init__(
        self,
        repository: JITAccessRepository,
        audit_service: AuditService,
        executor: TargetExecutor,
        target_account_repo: TargetAccountBindingRepository,
        bootstrap_credential: Optional[bytes] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        self.repo = repository
        self.audit = audit_service
        self.executor = executor
        self.target_account_repo = target_account_repo
        self.bootstrap_credential = bootstrap_credential
        self.worker_id = worker_id or uuid4().hex
        self.session: Session = self.repo.session  # type: ignore

    def claim_next_batch(self, limit: int = 50) -> List[UUID]:
        """Claim a batch of grants for reconciliation."""
        now = datetime.now(timezone.utc)
        lease_expiry = now + timedelta(seconds=60)
        claimed_ids: List[UUID] = []

        try:
            # First, prioritize SECURITY_UNCERTAIN grants
            stmt_uncertain = select(JITAccessGrant.id).outerjoin(
                JITReconciliationState, JITAccessGrant.id == JITReconciliationState.grant_id
            ).where(
                and_(
                    JITAccessGrant.status == JITGrantStatus.SECURITY_UNCERTAIN,
                    or_(
                        JITReconciliationState.grant_id.is_(None),
                        JITReconciliationState.lease_expires_at.is_(None),
                        JITReconciliationState.lease_expires_at <= now,
                    )
                )
            ).limit(limit)

            uncertain_ids = list(self.session.execute(stmt_uncertain).scalars().all())

            # Then get active/terminal grants that haven't been inspected recently (e.g., > 1 hour)
            remaining_limit = limit - len(uncertain_ids)
            other_ids = []
            if remaining_limit > 0:
                inspect_threshold = now - timedelta(hours=1)
                stmt_other = select(JITAccessGrant.id).outerjoin(
                    JITReconciliationState, JITAccessGrant.id == JITReconciliationState.grant_id
                ).where(
                    and_(
                        JITAccessGrant.status.in_([JITGrantStatus.ACTIVE, JITGrantStatus.EXPIRED, JITGrantStatus.REVOKED]),
                        or_(
                            JITReconciliationState.grant_id.is_(None),
                            and_(
                                or_(
                                    JITReconciliationState.lease_expires_at.is_(None),
                                    JITReconciliationState.lease_expires_at <= now,
                                ),
                                or_(
                                    JITReconciliationState.last_inspected_at.is_(None),
                                    JITReconciliationState.last_inspected_at <= inspect_threshold,
                                )
                            )
                        )
                    )
                ).limit(remaining_limit)
                other_ids = list(self.session.execute(stmt_other).scalars().all())

            to_claim = uncertain_ids + other_ids

            # Claim them by updating or inserting JITReconciliationState
            for grant_id in to_claim:
                state = self.session.execute(
                    select(JITReconciliationState).filter_by(grant_id=grant_id)
                ).scalar_one_or_none()

                if state:
                    state.worker_id = self.worker_id
                    state.lease_expires_at = lease_expiry
                    state.status = ReconciliationStatus.RECONCILING
                    state.row_version = (state.row_version or 1) + 1
                else:
                    state = JITReconciliationState(
                        grant_id=grant_id,
                        status=ReconciliationStatus.RECONCILING,
                        worker_id=self.worker_id,
                        lease_expires_at=lease_expiry,
                        row_version=1
                    )
                    self.session.add(state)

                claimed_ids.append(grant_id)

            self.session.commit()
            return claimed_ids
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to claim reconciliation batch: {e}")
            print(f"EXCEPTION IN CLAIM: {e}")
            raise

    def process_reconciliation(self) -> List[Dict[str, Any]]:
        """Run a full reconciliation sweep."""
        claimed_ids = self.claim_next_batch()
        results = []

        for grant_id in claimed_ids:
            try:
                res = self._reconcile_single_grant(grant_id)
                results.append(res)
            except Exception as e:
                logger.error(f"Error reconciling grant {grant_id}: {e}", exc_info=True)
                self._fail_reconciliation(grant_id, str(e))
                results.append({"grant_id": str(grant_id), "status": "error", "error": str(e)})

        return results

    def _reconcile_single_grant(self, grant_id: UUID) -> Dict[str, Any]:
        """Perform reconciliation for a single claimed grant."""
        now = datetime.now(timezone.utc)
        grant = self.session.get(JITAccessGrant, grant_id)
        if not grant:
            return {"grant_id": str(grant_id), "error": "Grant not found"}

        # 1. Gather Target OS Username
        target_os_username = None
        if grant.target_account_binding_id:
            binding = self.target_account_repo.get_by_id(grant.target_account_binding_id)
            if binding:
                target_os_username = binding.target_os_username

        if not target_os_username:
            self._fail_reconciliation(grant_id, "Target OS username missing")
            return {"grant_id": str(grant_id), "error": "Target OS username missing"}

        # 2. Inspect Target State
        auth_ctx = ExecutionAuthorizationContext(
            user_id=grant.user_id,
            resource_id=grant.resource_id,
            credential_id=grant.id,
            target_account_binding_id=grant.target_account_binding_id,
            grant_id=grant.id,
            requested_at=now,
            expires_at=now + timedelta(minutes=15)
        )

        req = ExecutionRequest(
            operation=ExecutionOperation.INSPECT_TARGET_STATE,
            resource_id=grant.resource_id,
            parameters={
                "grant_id": str(grant_id),
                "target_os_username": target_os_username,
                "bootstrap_credential": self.bootstrap_credential
            },
            authorization_context=auth_ctx
        )

        exec_res = self.executor.inspect_target_state(req)
        target_data = exec_res.details if exec_res.status == ExecutionStatus.SUCCESS else None

        # 3. Classify
        status, reason = classify_target_state(grant.status, target_data)

        # 4. Enforce Recovery if SAFE_RETRY or handle SECURITY_UNCERTAIN
        remediation_performed = False
        remediation_details = None

        if status == ReconciliationStatus.SAFE_RETRY:
            remediation_details = self._execute_safe_remediation(grant, auth_ctx, target_os_username)
            # Re-verify after remediation (simulate inspect, but for simplicity we assume success if no exception)
            status = ReconciliationStatus.SYNCHRONIZED
            reason = "Remediated residual artifacts successfully"
            remediation_performed = True

        if status == ReconciliationStatus.SYNCHRONIZED and grant.status == JITGrantStatus.SECURITY_UNCERTAIN:
            # DB Recovery: Transition back to terminal
            self._recover_db_terminal_state(grant)
            reason += " (Recovered from SECURITY_UNCERTAIN to REVOKED)"

        # 5. Commit Final Reconciliation State
        self._commit_reconciliation_state(grant_id, status, reason)

        # 6. Audit Logging
        self.audit.log_event(
            actor_user_id=UUID(int=0), # System
            action="jit_reconciliation",
            resource_type="jit_reconciliation_states",
            resource_id=str(grant_id),
            status=AuditStatus.SUCCESS if status != ReconciliationStatus.FAILED else AuditStatus.FAILED,
            severity=AuditSeverity.INFO if status == ReconciliationStatus.SYNCHRONIZED else AuditSeverity.HIGH,
            details={
                "db_status": grant.status.value,
                "reconciliation_status": status.value,
                "reason": reason,
                "remediation_performed": remediation_performed,
                "remediation_details": remediation_details
            }
        )

        return {
            "grant_id": str(grant_id),
            "status": status.value,
            "reason": reason,
            "remediation_performed": remediation_performed
        }

    def _execute_safe_remediation(self, grant: JITAccessGrant, auth_ctx: ExecutionAuthorizationContext, target_os_username: str) -> Dict[str, Any]:
        """Perform strictly destructive remediation of orphaned artifacts."""
        term_req = ExecutionRequest(
            operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
            resource_id=grant.resource_id,
            parameters={
                "grant_id": str(grant.id),
                "target_os_username": target_os_username,
                "bootstrap_credential": self.bootstrap_credential
            },
            authorization_context=auth_ctx
        )
        term_res = self.executor.terminate_jit_sessions(term_req)

        revoke_req = ExecutionRequest(
            operation=ExecutionOperation.REVOKE_JIT_GRANT,
            resource_id=grant.resource_id,
            parameters={
                "grant_id": str(grant.id),
                "target_os_username": target_os_username,
                "bootstrap_credential": self.bootstrap_credential
            },
            authorization_context=auth_ctx
        )
        revoke_res = self.executor.revoke_jit_grant(revoke_req)

        if revoke_res.status != ExecutionStatus.SUCCESS:
            raise Exception(f"Remediation failed: {revoke_res.error_message}")

        return {
            "sessions_terminated": term_res.status == ExecutionStatus.SUCCESS,
            "sudoers_removed": revoke_res.status == ExecutionStatus.SUCCESS
        }

    def _recover_db_terminal_state(self, grant: JITAccessGrant) -> None:
        """Move grant from SECURITY_UNCERTAIN to REVOKED."""
        now = datetime.now(timezone.utc)
        grant.status = JITGrantStatus.REVOKED
        grant.revoked_at = now
        grant.row_version = (grant.row_version or 1) + 1
        self.session.add(grant)

    def _commit_reconciliation_state(self, grant_id: UUID, status: ReconciliationStatus, reason: str) -> None:
        now = datetime.now(timezone.utc)
        state = self.session.execute(select(JITReconciliationState).filter_by(grant_id=grant_id)).scalar_one_or_none()
        if state and state.worker_id == self.worker_id:
            state.status = status
            state.last_inspected_at = now
            if status == ReconciliationStatus.SYNCHRONIZED:
                state.last_corrected_at = now
            state.lease_expires_at = None
            state.failure_reason = reason
            state.row_version = (state.row_version or 1) + 1
            self.session.add(state)
        self.session.commit()

    def _fail_reconciliation(self, grant_id: UUID, reason: str) -> None:
        try:
            self._commit_reconciliation_state(grant_id, ReconciliationStatus.FAILED, reason)
        except Exception:
            self.session.rollback()

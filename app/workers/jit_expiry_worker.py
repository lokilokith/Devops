"""JIT Expiry Worker – Phase 7.

Automates expiry enforcement and target-side privilege revocation for JIT grants.
Enforces the <= 5s observed overrun SLO under healthy worker operating conditions,
and guarantees recovery of backlogged expired grants upon worker restart.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.executor import TargetExecutor
from app.jit_access.service import JITAccessService
from app.workers.rotation_worker import WORKER_ACTOR_ID

logger = logging.getLogger(__name__)


class JITExpiryWorker:
    """Worker responsible for discovering, revoking, and recovering JIT access grants."""

    def __init__(
        self,
        service: JITAccessService,
        audit_service: Optional[AuditService] = None,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
        max_overrun_slo_ms: int = 5000,
        worker_id: str = "jit_expiry_worker_1",
    ) -> None:
        self.service = service
        self.audit_service = audit_service or service._audit
        self.executor = executor
        self.bootstrap_credential = bootstrap_credential
        self.max_overrun_slo_ms = max_overrun_slo_ms
        self.worker_id = worker_id

    def process_expired_grants(
        self, current_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Scan and revoke active grants whose expires_at is in the past.

        Uses UTC wall-clock time for authorization decisions, and monotonic clock
        for internal processing measurements.
        """
        now = current_time or datetime.now(timezone.utc)
        start_monotonic = time.monotonic()
        grants = self.service._repo.find_due_expired_grants(now)
        results: List[Dict[str, Any]] = []

        for grant in grants:
            grant_id_str = str(grant.id)
            try:
                updated_grant = self.service.expire_access(
                    grant.id,
                    executor=self.executor,
                    bootstrap_credential=self.bootstrap_credential,
                    worker_id=self.worker_id,
                )
                overrun_ms = updated_grant.observed_overrun_ms or 0
                is_slo_breach = overrun_ms > self.max_overrun_slo_ms

                if is_slo_breach:
                    logger.warning(
                        "JIT grant %s exceeded 5s overrun SLO: observed_overrun_ms=%d",
                        grant_id_str,
                        overrun_ms,
                    )
                    if self.audit_service:
                        self.audit_service.log_event(
                            actor_user_id=WORKER_ACTOR_ID,
                            action="jit_expiry_slo_breach",
                            resource_type="jit_access_grants",
                            resource_id=grant_id_str,
                            status=AuditStatus.FAILED,
                            severity=AuditSeverity.HIGH,
                            details={
                                "observed_overrun_ms": overrun_ms,
                                "slo_limit_ms": self.max_overrun_slo_ms,
                            },
                        )

                results.append(
                    {
                        "grant_id": grant_id_str,
                        "status": updated_grant.status.value,
                        "observed_overrun_ms": overrun_ms,
                        "slo_breach": is_slo_breach,
                    }
                )
            except Exception as e:
                logger.error(
                    "Failed to expire JIT grant %s: %s",
                    grant_id_str,
                    e,
                    exc_info=True,
                )
                results.append(
                    {
                        "grant_id": grant_id_str,
                        "status": "error",
                        "error": str(e),
                    }
                )

        duration_ms = (time.monotonic() - start_monotonic) * 1000.0
        logger.info(
            "JITExpiryWorker sweep completed: scanned=%d, processed=%d, duration_ms=%.2f",
            len(grants),
            len(results),
            duration_ms,
        )
        return results

    def process_interrupted_revocations(self) -> List[Dict[str, Any]]:
        """Recover any orphaned or interrupted revocations with expired leases."""
        return self.service._engine.recover_interrupted_revocations(
            executor=self.executor,
            bootstrap_credential=self.bootstrap_credential,
            worker_id=self.worker_id,
        )

    def run_recovery_on_startup(self) -> List[Dict[str, Any]]:
        """Worker-down scenario: drain backlogged expired grants and recover interrupted revocations."""
        logger.info(
            "JITExpiryWorker: Running startup recovery sweep for backlogged expired grants and interrupted revocations..."
        )
        rec_results = self.process_interrupted_revocations()
        exp_results = self.process_expired_grants()
        return rec_results + exp_results


def run_jit_expiry_job(
    service: JITAccessService,
    executor: Optional[TargetExecutor] = None,
    bootstrap_credential: Optional[bytes] = None,
    worker_id: str = "jit_expiry_worker_1",
) -> Dict[str, Any]:
    """Execute a single JIT expiry sweep job."""
    worker = JITExpiryWorker(
        service=service,
        executor=executor,
        bootstrap_credential=bootstrap_credential,
        worker_id=worker_id,
    )
    recovered = worker.process_interrupted_revocations()
    processed = worker.process_expired_grants()
    return {
        "recovered_count": len(recovered),
        "processed_count": len(processed),
        "results": recovered + processed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

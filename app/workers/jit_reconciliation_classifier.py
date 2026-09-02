import logging
from typing import Any, Dict, Tuple, Optional, Mapping

from app.jit_access.models import JITGrantStatus, ReconciliationStatus

logger = logging.getLogger(__name__)


def classify_target_state(
    db_status: JITGrantStatus, target_data: Optional[Mapping[str, Any]]
) -> Tuple[ReconciliationStatus, str]:
    """
    Pure classification engine for JIT Target Reconciliation.

    Returns:
        (ReconciliationStatus, diagnostic_reason)
    """
    if target_data is None:
        return ReconciliationStatus.UNREACHABLE, "Target unreachable or inspection failed"

    # Schema validation
    if not isinstance(target_data, dict):
        return ReconciliationStatus.MANUAL_INTERVENTION, "Malformed inspection response: not a dictionary"

    sudoers_present = target_data.get("sudoers_present")
    active_sessions = target_data.get("active_sessions")

    if sudoers_present is None or active_sessions is None:
        return ReconciliationStatus.MANUAL_INTERVENTION, "Malformed inspection response: missing expected fields"

    if not isinstance(active_sessions, list):
        return ReconciliationStatus.MANUAL_INTERVENTION, "Malformed inspection response: active_sessions is not a list"

    # Unknown artifacts must be escalated to manual intervention
    # Note: For our specific Phase 9 schema, any artifact reported in this valid
    # schema is assumed to be an OpsForge-owned artifact for THIS specific grant_id,
    # because the helper strictly uses opsforge-jit-<grant_id> and filters sessions by grant_id.
    # However, if the helper returned something malformed or cross-grant, we escalate.

    # Check if target state is completely clean
    is_clean = not sudoers_present and len(active_sessions) == 0

    if db_status == JITGrantStatus.ACTIVE:
        if is_clean:
            return ReconciliationStatus.DRIFTED, "ACTIVE grant missing target privilege (no privilege recreation allowed)"
        elif sudoers_present:
            # We don't check active_sessions here as 0 or N sessions are both valid for ACTIVE.
            return ReconciliationStatus.SYNCHRONIZED, "ACTIVE grant target state matches expectation"
        else:
            # Active but no sudoers, only sessions? That's drifted.
            return ReconciliationStatus.DRIFTED, "ACTIVE grant missing sudoers drop-in"

    elif db_status in (JITGrantStatus.EXPIRED, JITGrantStatus.REVOKED):
        if is_clean:
            return ReconciliationStatus.SYNCHRONIZED, "Terminal grant target state is cleanly removed"
        else:
            return ReconciliationStatus.SAFE_RETRY, "Terminal grant has residual OpsForge-owned artifacts/sessions"

    elif db_status == JITGrantStatus.SECURITY_UNCERTAIN:
        if is_clean:
            # Worker will use this to execute CAS DB transition to REVOKED
            return ReconciliationStatus.SYNCHRONIZED, "Uncertain grant proved cleanly removed"
        else:
            # Residual artifacts require SAFE_RETRY first
            return ReconciliationStatus.SAFE_RETRY, "Uncertain grant has verifiable residual artifacts to clean"

    elif db_status in (
        JITGrantStatus.PENDING,
        JITGrantStatus.REVOCATION_PENDING,
        JITGrantStatus.REVOCATION_RUNNING,
        JITGrantStatus.DENIED,
        JITGrantStatus.FAILED,
    ):
        # We don't expect to reconcile these transient/pre-creation states,
        # but if we do and they aren't clean, it's weird.
        if is_clean:
            return ReconciliationStatus.SYNCHRONIZED, f"Transient/failed state {db_status.value} is cleanly absent"
        else:
            return ReconciliationStatus.MANUAL_INTERVENTION, f"Unexpected target artifacts found for state {db_status.value}"

    return ReconciliationStatus.MANUAL_INTERVENTION, f"Unknown DB state {db_status}"

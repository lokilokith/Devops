from app.jit_access.models import JITGrantStatus, ReconciliationStatus
from app.workers.jit_reconciliation_classifier import classify_target_state


def test_classify_target_offline():
    status, reason = classify_target_state(JITGrantStatus.ACTIVE, None)
    assert status == ReconciliationStatus.UNREACHABLE
    assert "Target unreachable" in reason


def test_classify_active_synchronized():
    target_data = {"sudoers_present": True, "active_sessions": []}
    status, reason = classify_target_state(JITGrantStatus.ACTIVE, target_data)
    assert status == ReconciliationStatus.SYNCHRONIZED
    assert "ACTIVE grant target state matches expectation" in reason


def test_classify_active_drifted():
    target_data = {"sudoers_present": False, "active_sessions": []}
    status, reason = classify_target_state(JITGrantStatus.ACTIVE, target_data)
    assert status == ReconciliationStatus.DRIFTED
    assert "ACTIVE grant missing target privilege" in reason


def test_classify_revoked_synchronized():
    target_data = {"sudoers_present": False, "active_sessions": []}
    status, reason = classify_target_state(JITGrantStatus.REVOKED, target_data)
    assert status == ReconciliationStatus.SYNCHRONIZED
    assert "Terminal grant target state is cleanly removed" in reason


def test_classify_expired_synchronized():
    target_data = {"sudoers_present": False, "active_sessions": []}
    status, reason = classify_target_state(JITGrantStatus.EXPIRED, target_data)
    assert status == ReconciliationStatus.SYNCHRONIZED
    assert "Terminal grant target state is cleanly removed" in reason


def test_classify_revoked_safe_retry():
    target_data = {"sudoers_present": True, "active_sessions": []}
    status, reason = classify_target_state(JITGrantStatus.REVOKED, target_data)
    assert status == ReconciliationStatus.SAFE_RETRY
    assert "Terminal grant has residual OpsForge-owned artifacts" in reason


def test_classify_security_uncertain_synchronized():
    target_data = {"sudoers_present": False, "active_sessions": []}
    status, reason = classify_target_state(
        JITGrantStatus.SECURITY_UNCERTAIN, target_data
    )
    assert status == ReconciliationStatus.SYNCHRONIZED
    assert "Uncertain grant proved cleanly removed" in reason


def test_classify_security_uncertain_safe_retry():
    target_data = {"sudoers_present": True, "active_sessions": []}
    status, reason = classify_target_state(
        JITGrantStatus.SECURITY_UNCERTAIN, target_data
    )
    assert status == ReconciliationStatus.SAFE_RETRY
    assert "Uncertain grant has verifiable residual artifacts" in reason


def test_classify_unknown_state():
    from unittest.mock import Mock

    mock_status = Mock()
    mock_status.value = "UNKNOWN"
    status, reason = classify_target_state(
        mock_status, {"sudoers_present": False, "active_sessions": []}
    )
    assert status == ReconciliationStatus.MANUAL_INTERVENTION
    assert "Unknown DB state" in reason


def test_malformed_inspection():
    status, reason = classify_target_state(
        JITGrantStatus.ACTIVE, {"sudoers_present": True}
    )
    assert status == ReconciliationStatus.MANUAL_INTERVENTION
    assert "missing expected fields" in reason


def test_transient_state():
    status, reason = classify_target_state(
        JITGrantStatus.PENDING, {"sudoers_present": True, "active_sessions": []}
    )
    assert status == ReconciliationStatus.MANUAL_INTERVENTION
    assert "Unexpected target artifacts found for state pending" in reason

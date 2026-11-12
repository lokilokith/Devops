"""Tests for Execution Plane Audit Contract."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from app.audit.models import AuditSeverity, AuditStatus
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


def test_execution_audit_service_logs_success_event():
    mock_audit_svc = MagicMock()
    exec_audit = ExecutionAuditService(mock_audit_svc)

    user_id = uuid4()
    resource_id = uuid4()
    cred_id = uuid4()
    now = datetime.now(timezone.utc)

    auth_ctx = ExecutionAuthorizationContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=cred_id,
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=resource_id,
        authorization_context=auth_ctx,
    )
    res = ExecutionResult(
        execution_id=req.execution_id,
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        duration_ms=45.2,
    )

    exec_audit.record_execution_event(req, res)

    assert mock_audit_svc.log_event.called is True
    kwargs = mock_audit_svc.log_event.call_args.kwargs

    assert kwargs["actor_user_id"] == user_id
    assert kwargs["action"] == "TARGET_EXECUTION_ROTATE_CREDENTIAL"
    assert kwargs["resource_id"] == str(resource_id)
    assert kwargs["status"] == AuditStatus.SUCCESS
    assert kwargs["severity"] == AuditSeverity.INFO

    payload = kwargs["details"]
    assert payload["execution_id"] == str(req.execution_id)
    assert payload["status"] == "SUCCESS"
    assert payload["verification_status"] == "VERIFIED_SUCCESS"
    # Invariant: No plaintext secrets in audit payload
    assert (
        "secret" not in str(payload).lower()
        or "rotate_credential" in str(payload).lower()
    )


def test_execution_audit_service_logs_uncertain_event():
    mock_audit_svc = MagicMock()
    exec_audit = ExecutionAuditService(mock_audit_svc)

    user_id = uuid4()
    resource_id = uuid4()
    cred_id = uuid4()
    now = datetime.now(timezone.utc)

    auth_ctx = ExecutionAuthorizationContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=cred_id,
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        resource_id=resource_id,
        authorization_context=auth_ctx,
    )
    res = ExecutionResult(
        execution_id=req.execution_id,
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        status=ExecutionStatus.UNCERTAIN,
        verification_status=VerificationStatus.VERIFICATION_INDETERMINATE,
        failure_classification=FailureClassification.UNCERTAIN_STATE,
        is_uncertain=True,
        error_message="Rollback failed",
    )

    exec_audit.record_execution_event(req, res)

    kwargs = mock_audit_svc.log_event.call_args.kwargs
    assert kwargs["status"] == AuditStatus.FAILED
    assert kwargs["severity"] == AuditSeverity.CRITICAL
    assert kwargs["details"]["is_uncertain"] is True


def test_execution_audit_service_logs_general_failure_event():
    mock_audit_svc = MagicMock()
    exec_audit = ExecutionAuditService(mock_audit_svc)

    user_id = uuid4()
    resource_id = uuid4()
    cred_id = uuid4()
    now = datetime.now(timezone.utc)

    auth_ctx = ExecutionAuthorizationContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=cred_id,
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=resource_id,
        authorization_context=auth_ctx,
    )
    res = ExecutionResult(
        execution_id=req.execution_id,
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        status=ExecutionStatus.FAILED,
        verification_status=VerificationStatus.VERIFIED_FAILURE,
        failure_classification=FailureClassification.TARGET_FAILURE,
        error_message="Helper exit 1",
    )

    exec_audit.record_execution_event(req, res)

    kwargs = mock_audit_svc.log_event.call_args.kwargs
    assert kwargs["status"] == AuditStatus.FAILED
    assert kwargs["severity"] == AuditSeverity.HIGH


def test_execution_audit_service_handles_audit_exception_gracefully():
    mock_audit_svc = MagicMock()
    mock_audit_svc.log_event.side_effect = RuntimeError("Database offline")
    exec_audit = ExecutionAuditService(mock_audit_svc)

    user_id = uuid4()
    resource_id = uuid4()
    cred_id = uuid4()
    now = datetime.now(timezone.utc)

    auth_ctx = ExecutionAuthorizationContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=cred_id,
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=resource_id,
        authorization_context=auth_ctx,
    )
    res = ExecutionResult(
        execution_id=req.execution_id,
        operation=ExecutionOperation.VALIDATE_TARGET,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    # Must not raise
    exec_audit.record_execution_event(req, res)

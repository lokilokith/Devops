"""Execution Plane Audit Contract and Service.

Defines the audit event structure for all target-facing execution operations.
Strictly enforces the security invariant that no plaintext credentials, private
keys, or raw authentication secrets are ever persisted to audit logs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.domain import ExecutionRequest, ExecutionResult

logger = logging.getLogger(__name__)


class ExecutionAuditService:
    """Service for emitting sanitized audit records for Execution Plane operations."""

    def __init__(self, audit_service: AuditService) -> None:
        self._audit_service = audit_service

    def record_execution_event(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        actor_id: Optional[UUID] = None,
    ) -> None:
        """Record an execution event in the central audit log with strict secret redaction.

        Args:
            request: The execution request that was executed.
            result: The outcome of the execution.
            actor_id: The initiating user/actor identity (or fallback to auth context user).
        """
        effective_actor_id = actor_id or request.authorization_context.user_id

        # Determine audit status and severity based on execution result
        if result.is_success:
            audit_status = AuditStatus.SUCCESS
            severity = AuditSeverity.INFO
        elif result.is_uncertain:
            audit_status = AuditStatus.FAILED
            severity = AuditSeverity.CRITICAL
        else:
            audit_status = AuditStatus.FAILED
            severity = AuditSeverity.HIGH

        # Build sanitized audit payload (guaranteed zero secrets)
        event_payload: Dict[str, Any] = {
            "execution_id": str(result.execution_id),
            "operation": result.operation.value,
            "resource_id": str(request.resource_id),
            "status": result.status.value,
            "verification_status": result.verification_status.value,
            "failure_classification": (
                result.failure_classification.value
                if result.failure_classification
                else None
            ),
            "is_uncertain": result.is_uncertain,
            "error_message": result.error_message,
            "duration_ms": result.duration_ms,
            "idempotency_key": request.idempotency_key,
            "authorization_context": request.authorization_context.to_safe_dict(),
        }

        # Canonical audit action string
        action_name = f"TARGET_EXECUTION_{result.operation.value}"

        try:
            self._audit_service.log_event(
                actor_user_id=effective_actor_id,
                action=action_name,
                resource_type="RESOURCE",
                resource_id=str(request.resource_id),
                status=audit_status,
                severity=severity,
                details=event_payload,
            )
        except Exception as e:
            logger.error(
                "Failed to record execution audit event: %s",
                e,
                extra={
                    "execution_id": str(result.execution_id),
                    "operation": result.operation.value,
                },
            )

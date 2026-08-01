"""Audit Service for OpsForge."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.audit.models import AuditLog, AuditSeverity, AuditStatus
from app.audit.repository import AuditRepository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, audit_repo: AuditRepository) -> None:
        self._repo = audit_repo

    def log_event(
        self,
        actor_user_id: UUID,
        action: str,
        resource_type: str,
        status: AuditStatus,
        severity: AuditSeverity,
        target_user_id: UUID | None = None,
        resource_id: str | None = None,
        request_id: UUID | None = None,
        approval_workflow_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> AuditLog | None:
        try:
            event_id = f"EVT-{uuid.uuid4().hex.upper()}"
            audit_log = AuditLog(
                event_id=event_id,
                timestamp=datetime.now(timezone.utc),
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id,
                approval_workflow_id=approval_workflow_id,
                ip_address=ip_address,
                user_agent=user_agent,
                status=status,
                severity=severity,
                details=details,
            )
            return self._repo.create_log(audit_log)
        except Exception as err:
            logger.error(f"Audit logging failed: {err}")
            return None

    def log_login(
        self, actor_user_id: UUID, status: AuditStatus, ip_address: str | None = None
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            action="LOGIN",
            resource_type="SYSTEM",
            status=status,
            severity=(
                AuditSeverity.INFO
                if status == AuditStatus.SUCCESS
                else AuditSeverity.HIGH
            ),
            ip_address=ip_address,
        )

    def log_role_assignment(
        self,
        actor_user_id: UUID,
        target_user_id: UUID,
        role_id: UUID,
        status: AuditStatus,
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action="ASSIGN_ROLE",
            resource_type="roles",
            resource_id=str(role_id),
            status=status,
            severity=AuditSeverity.MEDIUM,
        )

    def log_permission_assignment(
        self,
        actor_user_id: UUID,
        role_id: UUID,
        permission_id: UUID,
        status: AuditStatus,
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            action="ASSIGN_PERMISSION",
            resource_type="permissions",
            resource_id=str(permission_id),
            status=status,
            severity=AuditSeverity.MEDIUM,
            details={"role_id": str(role_id)},
        )

    def log_access_request(
        self, actor_user_id: UUID, request_id: UUID, status: AuditStatus
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            action="SUBMIT_ACCESS_REQUEST",
            resource_type="ACCESS_REQUEST",
            resource_id=str(request_id),
            request_id=request_id,
            status=status,
            severity=AuditSeverity.INFO,
        )

    def log_approval(
        self, actor_user_id: UUID, approval_workflow_id: UUID, status: AuditStatus
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            action="PROCESS_APPROVAL",
            resource_type="APPROVAL_WORKFLOW",
            resource_id=str(approval_workflow_id),
            approval_workflow_id=approval_workflow_id,
            status=status,
            severity=AuditSeverity.INFO,
        )

    def log_authorization_denied(
        self, actor_user_id: UUID, resource_id: str, permission_action: str
    ) -> None:
        self.log_event(
            actor_user_id=actor_user_id,
            action="AUTHORIZATION_DENIED",
            resource_type="resources",
            resource_id=resource_id,
            status=AuditStatus.DENIED,
            severity=AuditSeverity.HIGH,
            details={"permission_action": permission_action},
        )


__all__ = ["AuditService"]

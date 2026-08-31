from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.access_requests.models import AccessRequestPriority, AccessRequestStatus
from app.access_requests.service import AccessRequestService
from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
)
from app.execution.executor import TargetExecutor
from app.execution.helper.opsforge_helper import COMMAND_CATALOG
from app.jit_access.exceptions import (
    GrantNotFoundError,
    InvalidGrantStateError,
    JITAccessError,
    UnauthorizedActivationError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.permissions.models import PermissionAction
from app.platform.extensions import db
from app.policy_engine.service import PolicyService
from app.shared.database import DbSession
from app.target_accounts.models import TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository


class JITAccessService:
    def __init__(
        self,
        repository: JITAccessRepository,
        access_request_service: AccessRequestService,
        policy_service: PolicyService,
        audit_service: AuditService,
        auth_service: AuthorizationService,
        target_account_repo: Optional[TargetAccountBindingRepository] = None,
        session: Optional[DbSession] = None,
    ) -> None:
        self._repo = repository
        self._ar_service = access_request_service
        self._policy_service = policy_service
        self._audit = audit_service
        self._auth = auth_service
        self._target_account_repo = (
            target_account_repo
            or TargetAccountBindingRepository(cast(Session, session or db.session))
        )
        self._session = session

    def request_access(
        self,
        requester_id: UUID,
        role_id: UUID,
        resource_id: UUID,
        duration_minutes: int,
        reason: str,
        command_set_id: Optional[str] = "system_health_check",
        context: dict | None = None,
    ) -> JITAccessGrant:
        # 1. Validate command_set_id against strict catalog (NO WILDCARDS)
        if not command_set_id or command_set_id not in COMMAND_CATALOG:
            raise JITAccessError(
                f"Invalid or unallowlisted command_set_id '{command_set_id}'. "
                f"Must be one of: {list(COMMAND_CATALOG.keys())}"
            )

        # 2. Check that user has an ACTIVE TargetAccountBinding on this resource
        binding = self._target_account_repo.find_by_user_and_resource(
            requester_id, resource_id
        )
        if not binding:
            raise JITAccessError(
                f"User has no target account on resource {resource_id}. "
                "Target account must be provisioned before JIT elevation."
            )
        if binding.status != TargetAccountBindingStatus.ACTIVE:
            raise JITAccessError(
                f"Target account on resource {resource_id} is not ACTIVE (status: {binding.status.value})."
            )

        # 3. Evaluate Policy Engine
        try:
            decision = self._policy_service.evaluate_policy(
                user_id=requester_id,
                action="create",
                resource_id="jit_grants",
                context={
                    "role_id": str(role_id),
                    "resource_id": str(resource_id),
                    "command_set_id": command_set_id,
                    **(context or {}),
                },
            )
            if decision.get("decision") != "ALLOW":
                raise JITAccessError(f"Policy denied: {decision.get('reason')}")

            # If duration exceeds policy limit
            if "max_duration_seconds" in decision and decision["max_duration_seconds"]:
                max_minutes = decision["max_duration_seconds"] / 60
                if duration_minutes > max_minutes:
                    raise JITAccessError(
                        f"Duration cannot exceed policy limit of {max_minutes} minutes"
                    )
        except Exception as e:
            if isinstance(e, JITAccessError):
                raise
            raise JITAccessError(f"Policy evaluation failed: {e}") from e

        # Limit hard duration to 8 hours (480 minutes) if no policy limit
        if duration_minutes > 480:
            raise JITAccessError("Duration cannot exceed maximum limit of 8 hours")

        # 4. Create AccessRequest
        try:
            ar = self._ar_service.submit_request(
                requester_id=requester_id,
                business_justification=reason,
                requested_role_id=None,
                requested_resource_id=resource_id,
                priority=AccessRequestPriority.MEDIUM,
            )
        except Exception as e:
            raise JITAccessError(f"Failed to submit access request: {e}") from e

        # 5. Create JITAccessGrant
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=duration_minutes)

        grant = JITAccessGrant(
            user_id=requester_id,
            role_id=role_id,
            resource_id=resource_id,
            target_account_binding_id=binding.id,
            command_set_id=command_set_id,
            approval_request_id=ar.id,
            status=JITGrantStatus.PENDING,
            expires_at=expires_at,
        )
        created_grant = self._repo.create(grant)

        # 6. Audit Event
        self._audit.log_event(
            actor_user_id=requester_id,
            action="jit.request_created",
            resource_type="jit_access_grants",
            resource_id=str(created_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "role_id": str(role_id),
                "resource_id": str(resource_id),
                "binding_id": str(binding.id),
                "command_set_id": command_set_id,
                "duration": duration_minutes,
            },
        )
        return created_grant

    def activate_grant(
        self,
        grant_id: UUID,
        user_id: UUID,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
    ) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)

        if grant.status == JITGrantStatus.ACTIVE:
            return grant

        if grant.status != JITGrantStatus.PENDING:
            raise InvalidGrantStateError(
                f"Only pending grants can be activated (status: {grant.status.value})"
            )

        # Check authorization: user cannot activate grants unless they are admin/authorized
        try:
            is_admin = self._auth.has_permission(
                user_id, "jit_grants", PermissionAction("update")
            )
            if not is_admin:
                raise UnauthorizedActivationError(
                    "User lacks permission to activate JIT grants"
                )
        except ValueError:
            raise UnauthorizedActivationError(
                "User lacks permission to activate JIT grants"
            )

        # Ensure associated AccessRequest is in APPROVED state
        ar = self._ar_service._repo.get_by_id(grant.approval_request_id)
        if not ar:
            raise JITAccessError("Associated access request not found")
        if ar.status != AccessRequestStatus.APPROVED:
            raise InvalidGrantStateError(
                f"Cannot activate grant. Access request is {ar.status.value}"
            )

        # Ensure associated TargetAccountBinding is ACTIVE
        binding = None
        if grant.target_account_binding_id:
            binding = self._target_account_repo.get_by_id(
                grant.target_account_binding_id
            )
        else:
            binding = self._target_account_repo.find_by_user_and_resource(
                grant.user_id, grant.resource_id
            )
            if binding:
                grant.target_account_binding_id = binding.id

        if not binding or binding.status != TargetAccountBindingStatus.ACTIVE:
            binding_status = binding.status.value if binding else "None"
            raise InvalidGrantStateError(
                f"Target account on resource {grant.resource_id} is not ACTIVE (status: {binding_status})."
            )

        if grant.expires_at and grant.expires_at < datetime.now(timezone.utc):
            raise InvalidGrantStateError("Grant has already expired before activation")

        # Target-side mutation via Execution Plane
        if executor:
            now_dt = datetime.now(timezone.utc)
            auth_ctx = ExecutionAuthorizationContext(
                user_id=user_id,
                resource_id=grant.resource_id,
                credential_id=binding.ssh_credential_id or grant.id,
                target_account_binding_id=binding.id,
                grant_id=grant.id,
                requested_at=now_dt,
                expires_at=grant.expires_at or (now_dt + timedelta(hours=8)),
            )
            req = ExecutionRequest(
                operation=ExecutionOperation.APPLY_JIT_GRANT,
                resource_id=grant.resource_id,
                parameters={
                    "grant_id": str(grant.id),
                    "target_os_username": binding.target_os_username,
                    "command_set_id": grant.command_set_id or "system_health_check",
                    "bootstrap_credential": bootstrap_credential,
                },
                authorization_context=auth_ctx,
            )
            exec_result = executor.apply_jit_grant(req)
            if exec_result.status != ExecutionStatus.SUCCESS:
                if (
                    exec_result.failure_classification
                    == FailureClassification.UNCERTAIN_STATE
                ):
                    grant.status = JITGrantStatus.SECURITY_UNCERTAIN
                    grant.failure_reason = (
                        exec_result.error_message
                        or "Security uncertainty during target verification"
                    )
                    self._repo.save(grant)
                    self._audit.log_event(
                        actor_user_id=user_id,
                        action="jit_grant_security_uncertainty",
                        resource_type="jit_access_grants",
                        resource_id=str(grant.id),
                        status=AuditStatus.FAILED,
                        severity=AuditSeverity.CRITICAL,
                        details={"error": grant.failure_reason},
                    )
                    raise JITAccessError(
                        f"JIT grant activation failed in security uncertainty: {grant.failure_reason}"
                    )
                else:
                    grant.status = JITGrantStatus.FAILED
                    grant.failure_reason = (
                        exec_result.error_message or "Execution failed"
                    )
                    self._repo.save(grant)
                    self._audit.log_event(
                        actor_user_id=user_id,
                        action="jit_grant_activation_failed",
                        resource_type="jit_access_grants",
                        resource_id=str(grant.id),
                        status=AuditStatus.FAILED,
                        severity=AuditSeverity.HIGH,
                        details={"error": grant.failure_reason},
                    )
                    raise JITAccessError(
                        f"JIT grant activation failed: {grant.failure_reason}"
                    )

        # Activate
        grant.status = JITGrantStatus.ACTIVE
        grant.activated_at = datetime.now(timezone.utc)
        grant.approved_by = ar.approved_by
        updated_grant = self._repo.save(grant)

        # Audit Event
        self._audit.log_event(
            actor_user_id=user_id,
            action="jit_grant_activated",
            resource_type="jit_access_grants",
            resource_id=str(grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.MEDIUM,
            details={
                "approved_by": str(ar.approved_by),
                "target_account_binding_id": str(grant.target_account_binding_id),
                "command_set_id": grant.command_set_id,
            },
        )
        return updated_grant

    def create_session(
        self,
        grant_id: UUID,
        system_actor_id: UUID,
        vault_service: Any,
        plaintext: bytes,
    ) -> Any:
        from sqlalchemy import select

        from app.jit_access.events import jit_session_created
        from app.jit_access.models import JITAccessSession

        grant = self._repo.get_by_id(grant_id)
        if grant.status != JITGrantStatus.ACTIVE:
            raise InvalidGrantStateError("Grant must be ACTIVE to create a session")

        # Check idempotency
        stmt = select(JITAccessSession).where(
            JITAccessSession.access_request_id == grant.approval_request_id
        )
        existing = db.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

        # Delegate secret creation to vault service
        secret = vault_service.create_secret(
            system_actor_id, grant.resource_id, plaintext
        )

        # Transition secret to JIT_EPHEMERAL
        from app.vault.domain import SecretStatus

        secret.status = SecretStatus.JIT_EPHEMERAL
        vault_service._repository.save(secret)
        db.session.commit()

        session = JITAccessSession(
            access_request_id=grant.approval_request_id,
            ephemeral_secret_id=secret.id,
            expires_at=grant.expires_at,
        )
        db.session.add(session)

        self._audit.log_event(
            actor_user_id=grant.user_id,
            action="JIT_SESSION_CREATED",
            resource_type="jit_access_sessions",
            resource_id=str(grant.approval_request_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={"grant_id": str(grant.id), "secret_id": str(secret.id)},
        )
        db.session.commit()

        jit_session_created.send(
            self,
            payload={
                "event": "jit_session_created",
                "session_id": str(grant.approval_request_id),
                "grant_id": str(grant.id),
                "actor_id": str(grant.user_id),
            },
        )
        return session

    def expire_access(
        self,
        grant_id: UUID,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
    ) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)
        if grant.status == JITGrantStatus.EXPIRED:
            return grant
        if grant.status != JITGrantStatus.ACTIVE:
            raise InvalidGrantStateError(
                f"Only active grants can be expired (status: {grant.status.value})"
            )

        grant.revocation_start = datetime.now(timezone.utc)

        if executor:
            now_dt = datetime.now(timezone.utc)
            auth_ctx = ExecutionAuthorizationContext(
                user_id=grant.user_id,
                resource_id=grant.resource_id,
                credential_id=grant.target_account_binding_id or grant.id,
                target_account_binding_id=grant.target_account_binding_id,
                grant_id=grant.id,
                requested_at=now_dt,
                expires_at=now_dt + timedelta(minutes=15),
            )
            req = ExecutionRequest(
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                resource_id=grant.resource_id,
                parameters={
                    "grant_id": str(grant.id),
                    "bootstrap_credential": bootstrap_credential,
                },
                authorization_context=auth_ctx,
            )
            exec_result = executor.revoke_jit_grant(req)
            if exec_result.status != ExecutionStatus.SUCCESS:
                grant.failure_reason = exec_result.error_message
                grant.status = JITGrantStatus.SECURITY_UNCERTAIN
                self._repo.save(grant)
                self._audit.log_event(
                    actor_user_id=grant.user_id,
                    action="jit.revocation_failed",
                    resource_type="jit_access_grants",
                    resource_id=str(grant.id),
                    status=AuditStatus.FAILED,
                    severity=AuditSeverity.CRITICAL,
                    details={"error": exec_result.error_message},
                )
                raise JITAccessError(
                    f"Failed to revoke JIT grant on target: {exec_result.error_message}"
                )

        grant.revocation_complete = datetime.now(timezone.utc)
        if grant.expires_at:
            grant.observed_overrun_ms = int(
                max(
                    0,
                    (grant.revocation_complete - grant.expires_at).total_seconds()
                    * 1000,
                )
            )

        grant.status = JITGrantStatus.EXPIRED
        updated_grant = self._repo.save(grant)

        from sqlalchemy import select

        from app.jit_access.events import jit_session_expired
        from app.jit_access.models import JITAccessSession

        stmt = select(JITAccessSession).where(
            JITAccessSession.access_request_id == grant.approval_request_id
        )
        session = db.session.execute(stmt).scalar_one_or_none()

        if session:
            if session.expire():
                db.session.add(session)
                self._audit.log_event(
                    actor_user_id=grant.user_id,
                    action="JIT_SESSION_EXPIRED",
                    resource_type="jit_access_sessions",
                    resource_id=str(session.access_request_id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                )
                jit_session_expired.send(
                    self,
                    payload={
                        "event": "jit_session_expired",
                        "session_id": str(session.access_request_id),
                        "grant_id": str(grant.id),
                        "actor_id": str(grant.user_id),
                    },
                )

        self._audit.log_event(
            actor_user_id=grant.user_id,
            action="jit.expired",
            resource_type="jit_access_grants",
            resource_id=str(updated_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "observed_overrun_ms": grant.observed_overrun_ms,
                "revocation_start": str(grant.revocation_start),
                "revocation_complete": str(grant.revocation_complete),
            },
        )
        return updated_grant

    def revoke_access(
        self,
        grant_id: UUID,
        revoker_id: UUID,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
    ) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)

        if grant.status == JITGrantStatus.REVOKED:
            return grant

        # Check authorization: non-admin cannot revoke another user's grant
        if grant.user_id != revoker_id:
            try:
                is_admin = self._auth.has_permission(
                    revoker_id, "jit_grants", PermissionAction("delete")
                )
                if not is_admin:
                    raise UnauthorizedActivationError(
                        "User cannot revoke another user's grant"
                    )
            except ValueError:
                raise UnauthorizedActivationError(
                    "User cannot revoke another user's grant"
                )

        if grant.status not in (JITGrantStatus.PENDING, JITGrantStatus.ACTIVE):
            raise InvalidGrantStateError(
                f"Only pending or active grants can be revoked (status: {grant.status.value})"
            )

        grant.revocation_start = datetime.now(timezone.utc)

        if executor and grant.status == JITGrantStatus.ACTIVE:
            now_dt = datetime.now(timezone.utc)
            auth_ctx = ExecutionAuthorizationContext(
                user_id=revoker_id,
                resource_id=grant.resource_id,
                credential_id=grant.target_account_binding_id or grant.id,
                target_account_binding_id=grant.target_account_binding_id,
                grant_id=grant.id,
                requested_at=now_dt,
                expires_at=now_dt + timedelta(minutes=15),
            )
            req = ExecutionRequest(
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                resource_id=grant.resource_id,
                parameters={
                    "grant_id": str(grant.id),
                    "bootstrap_credential": bootstrap_credential,
                },
                authorization_context=auth_ctx,
            )
            exec_result = executor.revoke_jit_grant(req)
            if exec_result.status != ExecutionStatus.SUCCESS:
                grant.failure_reason = exec_result.error_message
                grant.status = JITGrantStatus.SECURITY_UNCERTAIN
                self._repo.save(grant)
                self._audit.log_event(
                    actor_user_id=revoker_id,
                    action="jit.revocation_failed",
                    resource_type="jit_access_grants",
                    resource_id=str(grant.id),
                    status=AuditStatus.FAILED,
                    severity=AuditSeverity.CRITICAL,
                    details={"error": exec_result.error_message},
                )
                raise JITAccessError(
                    f"Failed to revoke JIT grant on target: {exec_result.error_message}"
                )

        grant.revocation_complete = datetime.now(timezone.utc)
        if grant.expires_at:
            grant.observed_overrun_ms = int(
                max(
                    0,
                    (grant.revocation_complete - grant.expires_at).total_seconds()
                    * 1000,
                )
            )

        grant.status = JITGrantStatus.REVOKED
        grant.revoked_at = grant.revocation_complete
        updated_grant = self._repo.save(grant)

        from sqlalchemy import select

        from app.jit_access.events import jit_session_revoked
        from app.jit_access.models import JITAccessSession

        stmt = select(JITAccessSession).where(
            JITAccessSession.access_request_id == grant.approval_request_id
        )
        session = db.session.execute(stmt).scalar_one_or_none()

        if session:
            if session.revoke():
                db.session.add(session)
                self._audit.log_event(
                    actor_user_id=revoker_id,
                    action="JIT_SESSION_REVOKED",
                    resource_type="jit_access_sessions",
                    resource_id=str(session.access_request_id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                )
                jit_session_revoked.send(
                    self,
                    payload={
                        "event": "jit_session_revoked",
                        "session_id": str(session.access_request_id),
                        "grant_id": str(grant.id),
                        "actor_id": str(revoker_id),
                    },
                )

        self._audit.log_event(
            actor_user_id=revoker_id,
            action="jit.revoked",
            resource_type="jit_access_grants",
            resource_id=str(updated_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "revoked_at": str(grant.revoked_at),
                "observed_overrun_ms": grant.observed_overrun_ms,
            },
        )
        return updated_grant

    def get_grant(self, grant_id: UUID) -> JITAccessGrant:
        """Fetch a JIT access grant by ID or raise GrantNotFoundError."""
        grant = self._repo.get_by_id(grant_id)
        if not grant:
            raise GrantNotFoundError(f"Grant {grant_id} not found")
        return grant

    def get_user_active_grants(self, user_id: UUID) -> List[JITAccessGrant]:
        """Fetch all active JIT grants for a user."""
        grants, _ = self._repo.list_grants(
            user_id=user_id, status=JITGrantStatus.ACTIVE
        )
        return grants

    def list_grants(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[JITGrantStatus] = None,
        page: int = 1,
        page_size: int = 50,
        **kwargs: Any,
    ) -> Tuple[List[JITAccessGrant], int]:
        """List grants with pagination."""
        offset = (page - 1) * page_size
        return self._repo.list_grants(
            user_id=user_id, status=status, limit=page_size, offset=offset
        )

    def check_and_expire(
        self,
        executor: Optional[TargetExecutor] = None,
        bootstrap_credential: Optional[bytes] = None,
    ) -> int:
        """Helper to find and expire all ACTIVE grants that have passed expires_at."""
        now = datetime.now(timezone.utc)
        grants = self._repo.find_due_expired_grants(now)
        count = 0
        for grant in grants:
            try:
                self.expire_access(
                    grant.id,
                    executor=executor,
                    bootstrap_credential=bootstrap_credential,
                )
                count += 1
            except Exception:
                pass
        return count

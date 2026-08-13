"""JIT Access Service."""

from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from uuid import UUID

from app.access_requests.models import AccessRequestPriority, AccessRequestStatus
from app.access_requests.service import AccessRequestService
from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.jit_access.exceptions import (
    GrantNotFoundError,
    InvalidGrantStateError,
    UnauthorizedActivationError,
    JITAccessError,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.permissions.models import PermissionAction
from app.policy_engine.service import PolicyService
from app.platform.extensions import db


class JITAccessService:
    def __init__(
        self,
        repository: JITAccessRepository,
        access_request_service: AccessRequestService,
        policy_service: PolicyService,
        audit_service: AuditService,
        auth_service: AuthorizationService,
    ) -> None:
        self._repo = repository
        self._ar_service = access_request_service
        self._policy_service = policy_service
        self._audit = audit_service
        self._auth = auth_service

    def request_access(
        self,
        requester_id: UUID,
        role_id: UUID,
        resource_id: UUID,
        duration_minutes: int,
        reason: str,
        context: dict | None = None,
    ) -> JITAccessGrant:
        # 1. Evaluate Policy Engine
        # We pass role_name, which requires resolving role ID. Assuming policy expects role names.
        # But wait, policy engine `evaluate_policy` takes user_id, action, resource_id, context.
        # Let's just use evaluate_policy to check if they are allowed to request JIT access for this resource.
        # Since JIT gives access to a resource via a role, we'll check permission 'jit.request' or similar.
        # Actually, let's evaluate against PolicyService with an action like 'create'
        # or we just rely on normal ABAC policies.
        # Wait, the prompt says "Policy Engine allows request"
        try:
            decision = self._policy_service.evaluate_policy(
                user_id=requester_id,
                action="create",
                resource_id="jit_grants",
                context={"role_id": str(role_id), "resource_id": str(resource_id), **(context or {})},
            )
            if decision.get("decision") != "ALLOW":
                raise JITAccessError(f"Policy denied: {decision.get('reason')}")
                
            # If duration exceeds policy limit
            if "max_duration_seconds" in decision and decision["max_duration_seconds"]:
                max_minutes = decision["max_duration_seconds"] / 60
                if duration_minutes > max_minutes:
                    raise JITAccessError(f"Duration cannot exceed policy limit of {max_minutes} minutes")
        except Exception as e:
            if isinstance(e, JITAccessError):
                raise
            # If policy evaluation fails due to some missing data, we deny
            raise JITAccessError(f"Policy evaluation failed: {e}") from e

        # Limit hard duration to 8 hours (480 minutes) if no policy limit
        if duration_minutes > 480:
            raise JITAccessError("Duration cannot exceed maximum limit of 8 hours")

        # 2. Create AccessRequest (we set role=None so Phase 1 doesn't auto-assign it)
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

        # 3. Create JITAccessGrant
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=duration_minutes)
        
        grant = JITAccessGrant(
            user_id=requester_id,
            role_id=role_id,
            resource_id=resource_id,
            approval_request_id=ar.id,
            status=JITGrantStatus.PENDING,
            expires_at=expires_at,
        )
        created_grant = self._repo.create(grant)

        # 4. Audit Event
        self._audit.log_event(
            actor_user_id=requester_id,
            action="jit.request_created",
            resource_type="jit_access_grants",
            resource_id=str(created_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={"role_id": str(role_id), "resource_id": str(resource_id), "duration": duration_minutes},
        )
        return created_grant

    def activate_grant(self, grant_id: UUID, user_id: UUID) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)
        
        if grant.status != JITGrantStatus.PENDING:
            raise InvalidGrantStateError("Only pending grants can be activated")

        # Check authorization: user cannot activate their own grant unless they are admin/authorized
        if grant.user_id == user_id:
            try:
                # Can the user activate grants? (Admins might)
                is_admin = self._auth.has_permission(user_id, "jit_grants", PermissionAction("update"))
                if not is_admin:
                    raise UnauthorizedActivationError("User cannot activate their own grant directly")
            except ValueError:
                raise UnauthorizedActivationError("User cannot activate their own grant directly")

        # Ensure associated AccessRequest is in APPROVED state
        ar = self._ar_service._repo.get_by_id(grant.approval_request_id)
        if not ar:
            raise JITAccessError("Associated access request not found")
        if ar.status != AccessRequestStatus.APPROVED:
            raise InvalidGrantStateError(f"Cannot activate grant. Access request is {ar.status.value}")

        # Activate
        grant.status = JITGrantStatus.ACTIVE
        grant.activated_at = datetime.now(timezone.utc)
        grant.approved_by = ar.approved_by
        
        # Recalculate expires_at from activation time (assuming duration is from requested_start/end or just keeping original duration relative to activation)
        # For simplicity, we just use the original expires_at if it's still in the future, or shift it.
        # Actually, let's keep it simple: the expires_at was set during creation. If it's already expired, fail.
        if grant.expires_at < datetime.now(timezone.utc):
            raise InvalidGrantStateError("Grant has already expired before activation")

        updated_grant = self._repo.update(grant)

        # Audit Event
        self._audit.log_event(
            actor_user_id=user_id,
            action="jit_grant_activated",
            resource_type="jit_access_grants",
            resource_id=str(grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.MEDIUM,
            details={"approved_by": str(ar.approved_by)},
        )
        return updated_grant


    def create_session(
        self, 
        grant_id: UUID, 
        system_actor_id: UUID,
        vault_service,
        plaintext: bytes
    ):
        from app.jit_access.models import JITAccessSession
        from app.jit_access.events import jit_session_created
        from sqlalchemy import select
        
        grant = self._repo.get_by_id(grant_id)
        if grant.status != JITGrantStatus.ACTIVE:
            raise InvalidGrantStateError("Grant must be ACTIVE to create a session")
            
        # Check idempotency
        stmt = select(JITAccessSession).where(JITAccessSession.access_request_id == grant.approval_request_id)
        existing = db.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

        # Delegate secret creation to vault service
        secret = vault_service.create_secret(system_actor_id, grant.resource_id, plaintext)
        
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
            details={"grant_id": str(grant.id), "secret_id": str(secret.id)}
        )
        db.session.commit()
        
        jit_session_created.send(
            self,
            payload={
                "event": "jit_session_created",
                "session_id": str(grant.approval_request_id),
                "grant_id": str(grant.id),
                "actor_id": str(grant.user_id),
            }
        )
        return session

    def expire_access(self, grant_id: UUID) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)
        if grant.status == JITGrantStatus.EXPIRED:
            return grant
        if grant.status != JITGrantStatus.ACTIVE:
            raise InvalidGrantStateError("Only active grants can be expired")
            
        grant.status = JITGrantStatus.EXPIRED
        updated_grant = self._repo.update(grant)
        
        from app.jit_access.models import JITAccessSession
        from app.jit_access.events import jit_session_expired
        from sqlalchemy import select
        stmt = select(JITAccessSession).where(JITAccessSession.access_request_id == grant.approval_request_id)
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
                    }
                )
        
        self._audit.log_event(
            actor_user_id=grant.user_id,
            action="jit.expired",
            resource_type="jit_access_grants",
            resource_id=str(updated_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        return updated_grant

    def revoke_access(self, grant_id: UUID, revoker_id: UUID) -> JITAccessGrant:
        grant = self._repo.get_by_id(grant_id)
        
        if grant.status == JITGrantStatus.REVOKED:
            return grant
            
        # Check authorization: non-admin cannot revoke another user's grant
        if grant.user_id != revoker_id:
            try:
                is_admin = self._auth.has_permission(revoker_id, "jit_grants", PermissionAction("delete"))
                if not is_admin:
                    raise UnauthorizedActivationError("User cannot revoke another user's grant")
            except ValueError:
                raise UnauthorizedActivationError("User cannot revoke another user's grant")

        if grant.status not in (JITGrantStatus.PENDING, JITGrantStatus.ACTIVE):
            raise InvalidGrantStateError("Only pending or active grants can be revoked")
            
        grant.status = JITGrantStatus.REVOKED
        grant.revoked_at = datetime.now(timezone.utc)
        updated_grant = self._repo.update(grant)
        
        from app.jit_access.models import JITAccessSession
        from app.jit_access.events import jit_session_revoked
        from sqlalchemy import select
        stmt = select(JITAccessSession).where(JITAccessSession.access_request_id == grant.approval_request_id)
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
                    }
                )
        
        self._audit.log_event(
            actor_user_id=revoker_id,
            action="jit.revoked",
            resource_type="jit_access_grants",
            resource_id=str(updated_grant.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        return updated_grant

    def check_and_expire(self) -> int:
        """Helper to find and expire all ACTIVE grants that have passed expires_at."""
        from sqlalchemy import select
        now = datetime.now(timezone.utc)
        stmt = select(JITAccessGrant).where(
            JITAccessGrant.status == JITGrantStatus.ACTIVE,
            JITAccessGrant.expires_at < now
        )
        grants = db.session.execute(stmt).scalars().all()
        count = 0
        for grant in grants:
            self.expire_access(grant.id)
            count += 1
        return count

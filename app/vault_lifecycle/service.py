"""Vault Lifecycle Service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.exceptions import AuthorizationDeniedError
from app.authorization.service import AuthorizationService
from app.permissions.models import PermissionAction
from app.vault_lifecycle.engine import RotationEligibilityEngine
from app.vault_lifecycle.exceptions import PolicyNotFoundError, PolicyValidationError
from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository

logger = logging.getLogger(__name__)


class VaultLifecycleService:
    """Orchestrates Vault Lifecycle policies and evaluation."""

    def __init__(
        self,
        repository: SecretRotationPolicyRepository,
        audit_service: AuditService,
        authz_service: AuthorizationService,
        session: Session,
    ) -> None:
        self._repository = repository
        self._audit = audit_service
        self._authz = authz_service
        self._session = session

    def create_policy(self, actor_id: UUID, data: dict) -> SecretRotationPolicy:
        # Authorization - Requires manage or create permission on vault_lifecycle
        try:
            self._authz.authorize(
                actor_id, "vault_lifecycle", PermissionAction("create")
            )
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="LIFECYCLE_POLICY_CREATE_FAILED",
                resource_type="secret_rotation_policies",
                resource_id="NEW",
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"},
            )
            self._session.commit()
            raise err

        vault_secret_id = data["vault_secret_id"]
        if self._repository.get_by_vault_secret_id(vault_secret_id):
            raise PolicyValidationError(
                f"Policy for secret {vault_secret_id} already exists"
            )

        # Initial dates
        now = datetime.now(timezone.utc)
        next_rot = now + timedelta(seconds=data["rotation_interval_seconds"])

        policy = SecretRotationPolicy(
            vault_secret_id=vault_secret_id,
            rotation_interval_seconds=data["rotation_interval_seconds"],
            last_rotated_at=None,
            next_rotation_at=next_rot,
            status=data.get("status", RotationStatus.ACTIVE),
            rotation_script_id=data.get("rotation_script_id"),
        )

        try:
            self._repository.save(policy)
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise PolicyValidationError(f"Invalid secret reference {vault_secret_id}")

        self._audit.log_event(
            actor_user_id=actor_id,
            action="LIFECYCLE_POLICY_CREATED",
            resource_type="secret_rotation_policies",
            resource_id=str(policy.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        self._session.commit()

        return policy

    def get_policy(self, actor_id: UUID, policy_id: UUID) -> SecretRotationPolicy:
        self._authz.authorize(actor_id, "vault_lifecycle", PermissionAction("read"))
        policy = self._repository.find_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError("Policy not found")
        return policy

    def update_policy(
        self, actor_id: UUID, policy_id: UUID, data: dict
    ) -> SecretRotationPolicy:
        try:
            self._authz.authorize(
                actor_id, "vault_lifecycle", PermissionAction("update")
            )
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="LIFECYCLE_POLICY_UPDATE_FAILED",
                resource_type="secret_rotation_policies",
                resource_id=str(policy_id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"},
            )
            self._session.commit()
            raise err

        policy = self._repository.find_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError("Policy not found")

        if "rotation_interval_seconds" in data:
            policy.rotation_interval_seconds = data["rotation_interval_seconds"]
            # Recalculate next rotation time
            last_rot = (
                policy.last_rotated_at
                or policy.created_at
                or datetime.now(timezone.utc)
            )
            if last_rot.tzinfo is None:
                last_rot = last_rot.replace(tzinfo=timezone.utc)
            policy.next_rotation_at = last_rot + timedelta(
                seconds=policy.rotation_interval_seconds
            )

        if "status" in data:
            policy.status = data["status"]

        if "rotation_script_id" in data:
            policy.rotation_script_id = data["rotation_script_id"]

        policy.updated_at = datetime.now(timezone.utc)
        self._repository.save(policy)
        self._session.commit()

        self._audit.log_event(
            actor_user_id=actor_id,
            action="LIFECYCLE_POLICY_UPDATED",
            resource_type="secret_rotation_policies",
            resource_id=str(policy.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        self._session.commit()

        return policy

    def delete_policy(self, actor_id: UUID, policy_id: UUID) -> None:
        try:
            self._authz.authorize(
                actor_id, "vault_lifecycle", PermissionAction("delete")
            )
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="LIFECYCLE_POLICY_DELETE_FAILED",
                resource_type="secret_rotation_policies",
                resource_id=str(policy_id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"},
            )
            self._session.commit()
            raise err

        policy = self._repository.find_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError("Policy not found")

        self._repository.delete(policy)
        self._session.commit()

        self._audit.log_event(
            actor_user_id=actor_id,
            action="LIFECYCLE_POLICY_DELETED",
            resource_type="secret_rotation_policies",
            resource_id=str(policy_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        self._session.commit()

    def evaluate_secret(self, actor_id: UUID, vault_secret_id: UUID) -> Dict[str, Any]:
        """Manually check a secret's rotation eligibility."""
        self._authz.authorize(actor_id, "vault_lifecycle", PermissionAction("read"))
        policy = self._repository.get_by_vault_secret_id(vault_secret_id)
        result = RotationEligibilityEngine.evaluate(policy)

        self._audit.log_event(
            actor_user_id=actor_id,
            action="LIFECYCLE_EVALUATED",
            resource_type="vault_secrets",
            resource_id=str(vault_secret_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details=result,
        )
        self._session.commit()
        return result

    def record_rotation(self, vault_secret_id: UUID) -> None:
        """
        Record a successful rotation. Updates timestamps.
        Does not commit - relies on the caller (vault rotation) to commit atomically.
        """
        policy = self._repository.get_by_vault_secret_id(vault_secret_id)
        if policy:
            from app.vault_lifecycle.models import RotationResultStatus

            now = datetime.now(timezone.utc)
            policy.last_rotated_at = now
            policy.next_rotation_at = now + timedelta(
                seconds=policy.rotation_interval_seconds
            )
            policy.last_rotation_status = RotationResultStatus.SUCCESS
            policy.updated_at = now
            self._repository.save(policy)

    def start_rotation(self, actor_id: UUID, vault_secret_id: UUID) -> None:
        """Domain transition to start rotation."""
        self._authz.authorize(actor_id, "vault_lifecycle", PermissionAction("update"))

        from app.vault.repository import SqlAlchemyVaultRepository

        secret_repo = SqlAlchemyVaultRepository(self._session)
        secret = secret_repo.find_by_id(vault_secret_id)
        if not secret:
            raise ValueError("Secret not found")

        secret.begin_rotation()
        secret_repo.save(secret)
        # Defer commit to caller for atomic rotation transaction

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_ROTATION_STARTED",
            resource_type="vault_secrets",
            resource_id=str(vault_secret_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        # Commit will be handled by the orchestrating caller

        from app.vault.events import secret_rotation_started

        secret_rotation_started.send(
            self,
            payload={
                "event": "secret_rotation_started",
                "secret_id": str(vault_secret_id),
                "actor_id": str(actor_id),
            },
        )

    def complete_rotation(
        self, actor_id: UUID, vault_secret_id: UUID, new_version
    ) -> None:
        """Domain transition to complete rotation."""
        self._authz.authorize(actor_id, "vault_lifecycle", PermissionAction("update"))

        from app.vault.repository import SqlAlchemyVaultRepository

        secret_repo = SqlAlchemyVaultRepository(self._session)
        secret = secret_repo.find_by_id(vault_secret_id)
        if not secret:
            raise ValueError("Secret not found")

        secret.complete_rotation(new_version)
        secret_repo.save(secret)

        from app.vault_lifecycle.models import RotationResultStatus

        policy = self._repository.get_by_vault_secret_id(vault_secret_id)
        if policy:
            now = datetime.now(timezone.utc)
            policy.last_rotated_at = now
            policy.next_rotation_at = now + timedelta(
                seconds=policy.rotation_interval_seconds
            )
            policy.last_rotation_status = RotationResultStatus.SUCCESS
            policy.updated_at = now
            self._repository.save(policy)

        # Defer commit to caller for atomic rotation transaction

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_ROTATION_COMPLETED",
            resource_type="vault_secrets",
            resource_id=str(vault_secret_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        # Commit will be handled by the orchestrating caller

        from app.vault.events import secret_rotation_completed

        secret_rotation_completed.send(
            self,
            payload={
                "event": "secret_rotation_completed",
                "secret_id": str(vault_secret_id),
                "actor_id": str(actor_id),
            },
        )

    def fail_rotation(self, actor_id: UUID, vault_secret_id: UUID, reason: str) -> None:
        """Domain transition to fail rotation (DESYNCED)."""
        self._authz.authorize(actor_id, "vault_lifecycle", PermissionAction("update"))

        from app.vault.repository import SqlAlchemyVaultRepository

        secret_repo = SqlAlchemyVaultRepository(self._session)
        secret = secret_repo.find_by_id(vault_secret_id)
        if not secret:
            raise ValueError("Secret not found")

        secret.fail_rotation()
        secret_repo.save(secret)

        from app.vault_lifecycle.models import RotationResultStatus

        policy = self._repository.get_by_vault_secret_id(vault_secret_id)
        if policy:
            policy.last_rotation_status = RotationResultStatus.FAILED
            policy.failure_reason = reason
            policy.updated_at = datetime.now(timezone.utc)
            self._repository.save(policy)

        # Defer commit to caller for atomic rotation transaction

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_ROTATION_FAILED",
            resource_type="vault_secrets",
            resource_id=str(vault_secret_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.HIGH,
            details={"reason": reason},
        )
        # Commit will be handled by the orchestrating caller

        from app.vault.events import secret_rotation_failed

        secret_rotation_failed.send(
            self,
            payload={
                "event": "secret_rotation_failed",
                "secret_id": str(vault_secret_id),
                "actor_id": str(actor_id),
                "reason": reason,
            },
        )

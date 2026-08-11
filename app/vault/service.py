"""Vault Application Service."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.exceptions import AuthorizationDeniedError
from app.authorization.service import AuthorizationService
from app.permissions.models import PermissionAction
from app.policy_engine.decisions import PolicyDecision
from app.policy_engine.engine import PolicyEngine
from app.vault.crypto import EncryptionService
from app.vault.domain import Secret, SecretDomainService, SecretFactory
from app.vault.events import (
    secret_access_denied,
    secret_accessed,
    secret_created,
    secret_deleted,
    secret_disabled,
    secret_rotated,
)
from app.vault.repository import SecretRepository

logger = logging.getLogger(__name__)


class ApprovalRequiredError(Exception):
    """Raised when vault access requires an approved AccessRequest."""
    def __init__(self, resource_id: UUID) -> None:
        self.resource_id = resource_id
        super().__init__("Vault access requires approval.")


class VaultApplicationService:
    """Orchestrates Vault use cases with strict architectural boundaries."""

    def __init__(
        self,
        domain_service: SecretDomainService,
        encryption_service: EncryptionService,
        repository: SecretRepository,
        policy_engine: PolicyEngine,
        audit_service: AuditService,
        authz_service: AuthorizationService,
        session: Session,
    ) -> None:
        self._domain_service = domain_service
        self._encryption_service = encryption_service
        self._repository = repository
        self._policy_engine = policy_engine
        self._audit = audit_service
        self._authz = authz_service
        self._session = session

    def list_secrets(self, actor_id: UUID) -> list[dict]:
        """List active secrets with hydrated resource data."""
        self._authz.authorize(actor_id, "vault", PermissionAction("read"))
        secrets = self._repository.list_active_secrets()
        
        from app.resources.repository import ResourcesRepository
        resource_repo = ResourcesRepository(self._session)
        
        results = []
        for secret in secrets:
            secret_dict = {
                "id": str(secret.id),
                "resource_id": str(secret.resource_id),
                "status": secret.status.value,
                "created_at": secret.created_at,
                "resource": None
            }
            try:
                res = resource_repo.get_by_id(secret.resource_id)
                if res:
                    secret_dict["resource"] = {
                        "id": str(res.id),
                        "resource_name": res.resource_name,
                        "resource_code": res.resource_code,
                        "resource_type": res.resource_type.value if res.resource_type else None
                    }
            except Exception:
                # If resource fails to load, just leave it as None
                pass
            results.append(secret_dict)
            
        return results

    def get_statistics(self, actor_id: UUID) -> dict:
        """Get vault statistics."""
        self._authz.authorize(actor_id, "vault", PermissionAction("read"))
        from app.vault.models import SecretStatus
        active = self._repository.count_by_status(SecretStatus.ACTIVE)
        disabled = self._repository.count_by_status(SecretStatus.DISABLED)
        recent = self._audit._repo.count(action="SECRET_RETRIEVED")
        return {
            "total_secrets": active + disabled,
            "active_secrets": active,
            "disabled_secrets": disabled,
            "recent_accesses": recent
        }

    def create_secret(self, actor_id: UUID, resource_id: UUID, plaintext: bytes) -> Secret:
        """Create a new secret (with implicit authorization check)."""
        # 1. Authorization (RBAC)
        try:
            self._authz.authorize(actor_id, "vault", PermissionAction("create"))
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_CREATE_FAILED",
                resource_type="vault_secrets",
                resource_id="NEW",
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"}
            )
            self._session.commit()
            raise err

        # 2. Domain Service builds aggregate
        secret = SecretFactory.create_new_secret(resource_id)

        # 3. Encryption Service wraps payload
        encrypted_dek, encrypted_payload, metadata = self._encryption_service.encrypt_payload(
            resource_id, secret.id, plaintext
        )

        # 4. Domain Service adds version
        from app.vault.domain import SecretVersion
        import uuid
        from datetime import datetime, timezone
        version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            created_by=actor_id
        )
        secret.add_version(version)

        # 5. Persist
        self._repository.save(secret)
        self._session.commit()

        # 6. Audit & Event
        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_CREATED",
            resource_type="vault_secrets",
            resource_id=str(secret.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        self._session.commit()
        secret_created.send(
            self,
            payload={
                "event": "secret_created",
                "secret_id": str(secret.id),
                "actor_id": str(actor_id),
                "resource_id": str(resource_id),
            }
        )

        return secret

    def retrieve_secret(self, actor_id: UUID, secret_id: UUID) -> bytes:
        """Retrieve and decrypt secret strictly honoring policies."""
        # Note: Do not load the secret blindly before RBAC/Policy checks if we know the resource.
        secret = self._repository.find_by_id(secret_id)
        if not secret:
            raise ValueError(f"Secret {secret_id} not found.")

        from app.vault.domain import SecretStatus
        if secret.status in (SecretStatus.DISABLED, SecretStatus.TOMBSTONED):
            raise ValueError(f"Cannot retrieve a secret in {secret.status.value} state.")

        # 1. Authorization (RBAC)
        try:
            self._authz.authorize(actor_id, "vault", PermissionAction("read"))
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_RETRIEVAL_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret.id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"}
            )
            self._session.commit()
            raise err

        # 2. Policy Engine evaluation
        decision = self._policy_engine.evaluate_vault_retrieval(actor_id, secret.resource_id)

        if decision == PolicyDecision.DENY:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_RETRIEVAL_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret.id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "Policy Engine Denied"}
            )
            self._session.commit()
            secret_access_denied.send(
                self,
                payload={
                    "event": "secret_access_denied",
                    "secret_id": str(secret.id),
                    "actor_id": str(actor_id),
                    "reason": "Policy DENY"
                }
            )
            raise AuthorizationDeniedError("Access to secret is explicitly denied by policy.")

        if decision == PolicyDecision.REQUIRE_APPROVAL:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_RETRIEVAL_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret.id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.MEDIUM,
                details={"reason": "Approval Required"}
            )
            self._session.commit()
            secret_access_denied.send(
                self,
                payload={
                    "event": "secret_access_denied",
                    "secret_id": str(secret.id),
                    "actor_id": str(actor_id),
                    "reason": "Policy REQUIRE_APPROVAL"
                }
            )
            raise ApprovalRequiredError(secret.resource_id)

        # 3. Decision is ALLOW. Retrieve current version
        version = secret.get_current_version()
        if not version:
            raise ValueError("Secret has no active versions.")

        # 4. Decrypt via EncryptionService
        plaintext = self._encryption_service.decrypt_payload(
            secret.resource_id,
            secret.id,
            version.encrypted_dek,
            version.encrypted_payload,
            version.metadata,
        )

        # 5. Events & Audit
        secret_accessed.send(
            self,
            payload={
                "event": "secret_accessed",
                "secret_id": str(secret.id),
                "actor_id": str(actor_id),
            }
        )
        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_RETRIEVED",
            resource_type="vault_secrets",
            resource_id=str(secret.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.HIGH,
        )
        self._session.commit()

        return plaintext

    def rotate_secret(self, actor_id: UUID, secret_id: UUID, new_plaintext: bytes) -> Secret:
        """Rotate a secret by adding a new encrypted version."""
        try:
            self._authz.authorize(actor_id, "vault", PermissionAction("update"))
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_ROTATE_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret_id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"}
            )
            self._session.commit()
            raise err

        secret = self._repository.find_by_id(secret_id)
        if not secret:
            raise ValueError("Secret not found")

        # Business rules checked in DomainService
        self._domain_service.ensure_can_rotate(secret)

        encrypted_dek, encrypted_payload, metadata = self._encryption_service.encrypt_payload(
            secret.resource_id, secret.id, new_plaintext
        )

        from app.vault.domain import SecretVersion
        import uuid
        from datetime import datetime, timezone
        version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            created_by=actor_id
        )
        secret.add_version(version)

        self._repository.save(secret)
        
        # Lifecycle integration: Record rotation atomically
        try:
            from app.vault_lifecycle.repository import SecretRotationPolicyRepository
            from app.vault_lifecycle.service import VaultLifecycleService
            lifecycle_repo = SecretRotationPolicyRepository(self._session)
            lifecycle_service = VaultLifecycleService(lifecycle_repo, self._audit, self._authz, self._session)
            lifecycle_service.record_rotation(secret.id)
        except Exception as e:
            logger.warning("Failed to record lifecycle rotation: %s", str(e))
            
        self._session.commit()

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_ROTATED",
            resource_type="vault_secrets",
            resource_id=str(secret.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        self._session.commit()
        secret_rotated.send(
            self,
            payload={
                "event": "secret_rotated",
                "secret_id": str(secret.id),
                "actor_id": str(actor_id),
            }
        )

        return secret

    def disable_secret(self, actor_id: UUID, secret_id: UUID) -> Secret:
        """Disable a secret."""
        try:
            self._authz.authorize(actor_id, "vault", PermissionAction("update"))
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_DISABLE_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret_id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"}
            )
            self._session.commit()
            raise err

        secret = self._repository.find_by_id(secret_id)
        if not secret:
            raise ValueError("Secret not found")

        secret.disable()

        self._repository.save(secret)
        self._session.commit()

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_DISABLED",
            resource_type="vault_secrets",
            resource_id=str(secret.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.MEDIUM,
        )
        self._session.commit()
        secret_disabled.send(
            self,
            payload={
                "event": "secret_disabled",
                "secret_id": str(secret.id),
                "actor_id": str(actor_id),
            }
        )

        return secret

    def delete_secret(self, actor_id: UUID, secret_id: UUID) -> None:
        """Delete/tombstone a secret."""
        try:
            self._authz.authorize(actor_id, "vault", PermissionAction("delete"))
        except AuthorizationDeniedError as err:
            self._audit.log_event(
                actor_user_id=actor_id,
                action="SECRET_DELETE_FAILED",
                resource_type="vault_secrets",
                resource_id=str(secret_id),
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": "RBAC Denied"}
            )
            self._session.commit()
            raise err

        secret = self._repository.find_by_id(secret_id)
        if not secret:
            raise ValueError("Secret not found")

        secret.tombstone()
        self._repository.save(secret)
        self._session.commit()

        self._audit.log_event(
            actor_user_id=actor_id,
            action="SECRET_DELETED",
            resource_type="vault_secrets",
            resource_id=str(secret_id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.HIGH,
        )
        self._session.commit()
        secret_deleted.send(
            self,
            payload={
                "event": "secret_deleted",
                "secret_id": str(secret_id),
                "actor_id": str(actor_id),
            }
        )


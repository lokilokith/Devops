"""Target Account Provisioning Service for OpsForge.

Orchestrates lazy provisioning, lifecycle transitions (PENDING -> ACTIVE -> SUSPENDED -> REMOVED),
Vault keypair creation, target-side helper execution, independent SSH verification, and audit logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
)
from app.execution.executor import TargetExecutor
from app.identity.models import UserStatus
from app.identity.repository import IdentityRepository
from app.resources.models import ResourceStatus
from app.resources.repository import ResourcesRepository
from app.target_accounts.models import (
    TargetAccountBinding,
    TargetAccountBindingStatus,
)
from app.target_accounts.repository import TargetAccountBindingRepository
from app.target_accounts.username import derive_target_username
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretFactory, SecretVersion
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault.ssh_keys import generate_ed25519_keypair

logger = logging.getLogger(__name__)


class TargetAccountService:
    """Orchestrates per-human, per-target OS identity provisioning and lifecycle."""

    def __init__(
        self,
        session: Session,
        binding_repo: TargetAccountBindingRepository,
        user_repo: IdentityRepository,
        resource_repo: ResourcesRepository,
        audit_service: AuditService,
        executor: TargetExecutor,
        encryption_service: EncryptionService,
    ) -> None:
        self._session = session
        self._binding_repo = binding_repo
        self._user_repo = user_repo
        self._resource_repo = resource_repo
        self._audit_service = audit_service
        self._executor = executor
        self._encryption_service = encryption_service

    def provision_target_account(
        self,
        user_id: UUID,
        resource_id: UUID,
        triggered_by_user_id: UUID,
        correlation_id: Optional[UUID] = None,
    ) -> TargetAccountBinding:
        """Provision a dedicated target OS account for a Control Plane user on a resource.

        Canonical trigger: First approved access request for (user, resource) pair.
        Idempotent: If an ACTIVE binding already exists, it is returned without duplicate creation.
        """
        now = datetime.now(timezone.utc)
        corr_id = correlation_id or uuid4()

        # 1. Validate User
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"Control plane user {user_id} does not exist.")
        if user.status != UserStatus.ACTIVE:
            raise ValueError(
                f"Control plane user {user_id} is {user.status.value}, cannot provision target account."
            )

        # 2. Validate Resource
        resource = self._resource_repo.get_by_id(resource_id)
        if not resource:
            raise ValueError(f"Resource {resource_id} does not exist.")
        if resource.status != ResourceStatus.ACTIVE:
            raise ValueError(
                f"Resource {resource_id} is {resource.status.value}, cannot provision target account."
            )

        # 3. Check Existing Binding (Idempotency)
        existing_binding = self._binding_repo.find_by_user_and_resource(
            user_id, resource_id
        )
        if existing_binding:
            if existing_binding.status == TargetAccountBindingStatus.ACTIVE:
                logger.info(
                    "TargetAccountService: Binding already ACTIVE for user %s on resource %s",
                    user_id,
                    resource_id,
                )
                return existing_binding
            elif existing_binding.status == TargetAccountBindingStatus.SUSPENDED:
                raise ValueError(
                    "Target account binding is SUSPENDED. Reactivation requires explicit policy."
                )
            elif existing_binding.status == TargetAccountBindingStatus.REMOVED:
                raise ValueError(
                    "Target account binding was REMOVED. Re-creation requires new provisioning flow."
                )

        # 4. Deterministic Username Derivation
        existing_os_users = self._binding_repo.get_existing_os_usernames(resource_id)
        target_os_username = derive_target_username(user.username, existing_os_users)

        # 5. Create or reuse PENDING binding row
        if not existing_binding:
            binding = TargetAccountBinding(
                control_plane_user_id=user_id,
                resource_id=resource_id,
                target_os_username=target_os_username,
                status=TargetAccountBindingStatus.PENDING,
            )
            binding = self._binding_repo.create(binding)
            self._session.commit()
        else:
            binding = existing_binding

        # 6. Generate Dedicated Ed25519 Keypair in Vault Plane
        priv_pem, pub_ssh = generate_ed25519_keypair(
            comment=f"opsforge-{binding.id.hex[:8]}"
        )

        vault_repo = SqlAlchemyVaultRepository(self._session)
        vault_secret = SecretFactory.create_new_secret(resource_id)
        encrypted_dek, encrypted_payload, metadata = (
            self._encryption_service.encrypt_payload(
                resource_id, vault_secret.id, priv_pem.encode("utf-8")
            )
        )
        version = SecretVersion(
            id=uuid4(),
            secret_id=vault_secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=now,
            created_by=triggered_by_user_id,
        )
        vault_secret.add_version(version)
        vault_repo.save(vault_secret)
        self._session.commit()

        # 7. Obtain bootstrap credential for target execution
        bootstrap_cred_bytes = b""
        bootstrap_secret = vault_repo.find_by_resource(resource_id)
        if (
            bootstrap_secret
            and bootstrap_secret.id != vault_secret.id
            and bootstrap_secret.current_version_id
        ):
            curr_ver = next(
                (
                    v
                    for v in bootstrap_secret.versions
                    if v.id == bootstrap_secret.current_version_id
                ),
                None,
            )
            if curr_ver:
                bootstrap_cred_bytes = self._encryption_service.decrypt_payload(
                    resource_id,
                    bootstrap_secret.id,
                    curr_ver.encrypted_dek,
                    curr_ver.encrypted_payload,
                    curr_ver.metadata,
                )

        # 8. Construct Execution Authorization Context & Request
        auth_ctx = ExecutionAuthorizationContext(
            user_id=user_id,
            resource_id=resource_id,
            target_account_binding_id=binding.id,
            credential_id=vault_secret.id,
            requested_at=now,
            expires_at=now + timedelta(minutes=15),
        )

        exec_request = ExecutionRequest(
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            resource_id=resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": resource.hostname_ip or resource.resource_code,
                "port": resource.port or 22,
                "target_os_username": target_os_username,
                "public_key": pub_ssh,
                "bootstrap_credential": bootstrap_cred_bytes,
                "user_private_key": priv_pem.encode("utf-8"),
            },
        )

        # 9. Execute Provisioning and Target-Side Verification via Execution Plane
        exec_result = self._executor.provision_account(exec_request)

        # Zeroize sensitive plaintext in-memory references immediately
        del priv_pem
        del bootstrap_cred_bytes

        # 10. Process Outcome
        if exec_result.status == ExecutionStatus.SUCCESS:
            binding.status = TargetAccountBindingStatus.ACTIVE
            binding.ssh_credential_id = vault_secret.id
            binding.last_verified_at = datetime.now(timezone.utc)
            binding.failure_reason = None
            self._binding_repo.save(binding)

            self._audit_service.log_event(
                actor_user_id=triggered_by_user_id,
                action="target_account.provisioned",
                resource_type="target_account_bindings",
                resource_id=str(binding.id),
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={
                    "control_plane_user_id": str(user_id),
                    "resource_id": str(resource_id),
                    "target_os_username": target_os_username,
                    "ssh_credential_id": str(vault_secret.id),
                    "correlation_id": str(corr_id),
                },
            )
            self._session.commit()
            return binding

        # Handle Failure
        binding.status = TargetAccountBindingStatus.PENDING
        binding.failure_reason = exec_result.error_message or "Provisioning failed"
        self._binding_repo.save(binding)

        severity = (
            AuditSeverity.CRITICAL
            if exec_result.failure_classification
            == FailureClassification.UNCERTAIN_STATE
            else AuditSeverity.HIGH
        )

        self._audit_service.log_event(
            actor_user_id=triggered_by_user_id,
            action="target_account.provision_failed",
            resource_type="target_account_bindings",
            resource_id=str(binding.id),
            status=AuditStatus.FAILED,
            severity=severity,
            details={
                "control_plane_user_id": str(user_id),
                "resource_id": str(resource_id),
                "target_os_username": target_os_username,
                "error": exec_result.error_message,
                "classification": (
                    exec_result.failure_classification.value
                    if exec_result.failure_classification
                    else "UNKNOWN"
                ),
                "correlation_id": str(corr_id),
            },
        )
        self._session.commit()

        raise RuntimeError(
            f"Target account provisioning failed for '{target_os_username}' on resource {resource_id}: {exec_result.error_message}"
        )

    def remove_target_account(
        self,
        binding_id: UUID,
        actor_user_id: UUID,
    ) -> TargetAccountBinding:
        """Remove a target account binding and its corresponding target OS account."""
        now = datetime.now(timezone.utc)
        binding = self._binding_repo.get_by_id(binding_id)
        if not binding:
            raise ValueError(f"TargetAccountBinding {binding_id} not found.")

        resource = self._resource_repo.get_by_id(binding.resource_id)
        if not resource:
            raise ValueError(f"Resource {binding.resource_id} not found.")

        # Obtain bootstrap credential
        vault_repo = SqlAlchemyVaultRepository(self._session)
        bootstrap_secret = vault_repo.find_by_resource(binding.resource_id)

        bootstrap_cred_bytes = b""
        if (
            bootstrap_secret
            and bootstrap_secret.id != binding.ssh_credential_id
            and bootstrap_secret.current_version_id
        ):
            curr_ver = next(
                (
                    v
                    for v in bootstrap_secret.versions
                    if v.id == bootstrap_secret.current_version_id
                ),
                None,
            )
            if curr_ver:
                bootstrap_cred_bytes = self._encryption_service.decrypt_payload(
                    binding.resource_id,
                    bootstrap_secret.id,
                    curr_ver.encrypted_dek,
                    curr_ver.encrypted_payload,
                    curr_ver.metadata,
                )

        auth_ctx = ExecutionAuthorizationContext(
            user_id=binding.control_plane_user_id,
            resource_id=binding.resource_id,
            target_account_binding_id=binding.id,
            credential_id=binding.ssh_credential_id
            or UUID("00000000-0000-0000-0000-000000000001"),
            requested_at=now,
            expires_at=now + timedelta(minutes=15),
        )

        exec_request = ExecutionRequest(
            operation=ExecutionOperation.REMOVE_ACCOUNT,
            resource_id=binding.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": resource.hostname_ip or resource.resource_code,
                "port": resource.port or 22,
                "target_os_username": binding.target_os_username,
                "bootstrap_credential": bootstrap_cred_bytes,
            },
        )

        exec_result = self._executor.remove_account(exec_request)
        del bootstrap_cred_bytes

        if exec_result.status == ExecutionStatus.SUCCESS:
            binding.status = TargetAccountBindingStatus.REMOVED
            self._binding_repo.save(binding)

            self._audit_service.log_event(
                actor_user_id=actor_user_id,
                action="target_account.removed",
                resource_type="target_account_bindings",
                resource_id=str(binding.id),
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={
                    "control_plane_user_id": str(binding.control_plane_user_id),
                    "resource_id": str(binding.resource_id),
                    "target_os_username": binding.target_os_username,
                },
            )
            self._session.commit()
            return binding

        self._audit_service.log_event(
            actor_user_id=actor_user_id,
            action="target_account.remove_failed",
            resource_type="target_account_bindings",
            resource_id=str(binding.id),
            status=AuditStatus.FAILED,
            severity=AuditSeverity.HIGH,
            details={
                "control_plane_user_id": str(binding.control_plane_user_id),
                "resource_id": str(binding.resource_id),
                "target_os_username": binding.target_os_username,
                "error": exec_result.error_message,
            },
        )
        self._session.commit()
        raise RuntimeError(
            f"Failed to remove target account '{binding.target_os_username}': {exec_result.error_message}"
        )

    def suspend_target_account(
        self,
        binding_id: UUID,
        actor_user_id: UUID,
    ) -> TargetAccountBinding:
        """Suspend a target account binding (preserves OS account for forensic audit)."""
        binding = self._binding_repo.get_by_id(binding_id)
        if not binding:
            raise ValueError(f"TargetAccountBinding {binding_id} not found.")

        binding.status = TargetAccountBindingStatus.SUSPENDED
        self._binding_repo.save(binding)

        self._audit_service.log_event(
            actor_user_id=actor_user_id,
            action="target_account.suspended",
            resource_type="target_account_bindings",
            resource_id=str(binding.id),
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
            details={
                "control_plane_user_id": str(binding.control_plane_user_id),
                "resource_id": str(binding.resource_id),
                "target_os_username": binding.target_os_username,
            },
        )
        self._session.commit()
        return binding

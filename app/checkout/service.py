"""Checkout Service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from sqlalchemy.orm import Session

from app.access_requests.models import AccessRequestStatus
from app.access_requests.repository import AccessRequestRepository
from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.checkout.exceptions import (
    CheckoutError,
    InvalidCheckoutStateError,
    LeaseNotFoundError,
    UnauthorizedCheckoutError,
)
from app.checkout.models import CredentialLease, LeaseStatus
from app.checkout.repository import CredentialLeaseRepository
from app.vault.crypto import EncryptionService
from app.vault.domain import SecretStatus
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault.exceptions import ConcurrencyError

logger = logging.getLogger(__name__)


class CheckoutService:
    def __init__(
        self,
        session: Session,
        lease_repo: CredentialLeaseRepository,
        vault_repo: SqlAlchemyVaultRepository,
        policy_repo: SecretRotationPolicyRepository,
        ar_repo: AccessRequestRepository,
        audit_service: AuditService,
        authz_service: AuthorizationService,
        encryption_service: EncryptionService,
    ):
        self._session = session
        self._lease_repo = lease_repo
        self._vault_repo = vault_repo
        self._policy_repo = policy_repo
        self._ar_repo = ar_repo
        self._audit = audit_service
        self._authz = authz_service
        self._crypto = encryption_service

    def checkout(self, user_id: UUID, access_request_id: UUID) -> bytes:
        """Atomically checks out a VaultSecret and returns its plaintext."""
        try:
            with self._session.begin_nested():
                # 1. Access Request validation
                ar = self._ar_repo.get_by_id(access_request_id)
                if not ar:
                    raise CheckoutError(f"Access Request {access_request_id} not found")
                
                # 2. Verify request belongs to the requesting user
                if ar.requester_id != user_id:
                    raise UnauthorizedCheckoutError("Request does not belong to the user")
                
                # 3. Verify request is APPROVED
                if ar.status != AccessRequestStatus.APPROVED:
                    raise InvalidCheckoutStateError(f"Request is not APPROVED (status: {ar.status.value})")

                # 4. Verify window has not expired
                now = datetime.now(timezone.utc)
                if ar.requested_end:
                    ar_end = ar.requested_end
                    if ar_end.tzinfo is None:
                        ar_end = ar_end.replace(tzinfo=timezone.utc)
                    if ar_end < now:
                        raise InvalidCheckoutStateError("Access request window has expired")

                # 5. RBAC Authorization is implicit via Access Request approval, but we can double check
                # For Phase 2C, having an APPROVED access request is the authorization token.
                
                # 6. Locate the VaultSecret
                secret = self._vault_repo.find_by_resource(ar.requested_resource_id)
                if not secret:
                    raise CheckoutError("No VaultSecret found for the requested resource")

                # 7. Verify VaultSecret is ACTIVE
                if secret.status != SecretStatus.ACTIVE:
                    raise InvalidCheckoutStateError(f"VaultSecret is not ACTIVE (status: {secret.status.value})")

                # 8. Atomically transition ACTIVE -> CHECKED_OUT using row_version CAS
                secret.checkout()
                self._vault_repo.save(secret)

                # 9. Create CredentialLease
                lease = CredentialLease(
                    vault_secret_id=secret.id,
                    user_id=user_id,
                    access_request_id=ar.id,
                    status=LeaseStatus.ACTIVE,
                    started_at=now,
                    expires_at=ar.requested_end or (now + datetime.timedelta(hours=1))
                )
                self._lease_repo.save(lease)

                # 10. Audit event
                self._audit.log_event(
                    actor_user_id=user_id,
                    action="CHECKOUT_SUCCESS",
                    resource_type="credential_leases",
                    resource_id=str(lease.id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={
                        "secret_id": str(secret.id),
                        "access_request_id": str(ar.id),
                    }
                )
            
            # 11. Commit transaction (outer commit usually handled by caller, but we flush/commit the work)
            self._session.commit()
            
        except ConcurrencyError:
            self._session.rollback()
            self._audit.log_event(
                actor_user_id=user_id,
                action="CHECKOUT_CONCURRENCY_CONFLICT",
                resource_type="vault_secrets",
                resource_id=str(ar.requested_resource_id),
                status=AuditStatus.FAILED,
                severity=AuditSeverity.MEDIUM,
                details={"access_request_id": str(access_request_id)}
            )
            self._session.commit()
            raise InvalidCheckoutStateError("Checkout conflict: another user checked out this secret.")
        except Exception as e:
            self._session.rollback()
            self._audit.log_event(
                actor_user_id=user_id,
                action="CHECKOUT_DENIED",
                resource_type="vault_secrets",
                resource_id=str(ar.requested_resource_id) if 'ar' in locals() and ar else None,
                status=AuditStatus.DENIED,
                severity=AuditSeverity.HIGH,
                details={"reason": str(e)}
            )
            self._session.commit()
            raise

        # 12. Decrypt for immediate retrieval (ONLY after commit)
        try:
            # We must fetch the latest secret version to decrypt
            # secret object is still in memory but we need the actual version entity.
            current_version = secret.get_current_version()
            if not current_version:
                raise CheckoutError("VaultSecret has no current version")

            plaintext = self._crypto.decrypt_payload(
                secret.resource_id,
                secret.id,
                current_version.encrypted_dek,
                current_version.encrypted_payload,
                current_version.metadata,
            )
            return plaintext
        except Exception:
            # If decryption fails, the lease is still ACTIVE. User might need to check-in or it expires.
            raise CheckoutError("Failed to decrypt the checked-out credential")


    def _checkin_internal(self, lease: CredentialLease, actor_id: UUID, new_status: LeaseStatus, action: str) -> None:
        """Internal helper for Check-in, Expiration, and Revocation."""
        try:
            with self._session.begin_nested():
                # Transition Lease
                lease.status = new_status
                now = datetime.now(timezone.utc)
                if new_status == LeaseStatus.RETURNED:
                    lease.returned_at = now
                elif new_status == LeaseStatus.REVOKED:
                    lease.revoked_at = now
                
                self._lease_repo.save(lease)

                # Transition Secret CHECKED_OUT -> ROTATING
                secret = self._vault_repo.find_by_id(lease.vault_secret_id)
                if secret and secret.status == SecretStatus.CHECKED_OUT:
                    secret.check_in_to_rotate()
                    self._vault_repo.save(secret)
                
                # Schedule for rotation
                policy = self._policy_repo.get_by_vault_secret_id(lease.vault_secret_id)
                if policy:
                    policy.next_rotation_at = now
                    self._policy_repo.save(policy)

                # Audit
                self._audit.log_event(
                    actor_user_id=actor_id,
                    action=action,
                    resource_type="credential_leases",
                    resource_id=str(lease.id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={"secret_id": str(lease.vault_secret_id)}
                )
            self._session.commit()
        except ConcurrencyError:
            self._session.rollback()
            raise InvalidCheckoutStateError("Concurrency conflict during check-in")
        except Exception:
            self._session.rollback()
            raise


    def checkin(self, user_id: UUID, lease_id: UUID) -> None:
        """Manually return a checked-out credential."""
        lease = self._lease_repo.get_by_id(lease_id)
        if not lease:
            raise LeaseNotFoundError("Lease not found")
        
        if lease.user_id != user_id:
            raise UnauthorizedCheckoutError("User does not own this lease")

        if lease.status != LeaseStatus.ACTIVE:
            raise InvalidCheckoutStateError(f"Lease is not ACTIVE (status: {lease.status.value})")

        self._checkin_internal(lease, user_id, LeaseStatus.RETURNED, "CHECKIN_SUCCESS")


    def expire(self, lease_id: UUID) -> None:
        """Expire a lease that has passed its expires_at."""
        lease = self._lease_repo.get_by_id(lease_id)
        if not lease:
            raise LeaseNotFoundError("Lease not found")
        
        if lease.status != LeaseStatus.ACTIVE:
            return # Ignore if already returned or revoked

        now = datetime.now(timezone.utc)
        expires_at = lease.expires_at.replace(tzinfo=timezone.utc) if lease.expires_at.tzinfo is None else lease.expires_at
        if expires_at > now:
            raise InvalidCheckoutStateError("Lease has not yet expired")

        # Expiration is typically done by a system worker, so actor is the system
        system_actor_id = UUID("00000000-0000-0000-0000-000000000001")
        self._checkin_internal(lease, system_actor_id, LeaseStatus.EXPIRED, "LEASE_EXPIRED")


    def revoke(self, admin_id: UUID, lease_id: UUID) -> None:
        """Administratively revoke an active lease."""
        # Check authorization
        from app.permissions.models import PermissionAction
        try:
            self._authz.authorize(admin_id, "vault_secrets", PermissionAction("delete"))
        except Exception as e:
            raise UnauthorizedCheckoutError("Admin is not authorized to revoke leases") from e

        lease = self._lease_repo.get_by_id(lease_id)
        if not lease:
            raise LeaseNotFoundError("Lease not found")
        
        if lease.status != LeaseStatus.ACTIVE:
            raise InvalidCheckoutStateError(f"Lease is not ACTIVE (status: {lease.status.value})")

        self._checkin_internal(lease, admin_id, LeaseStatus.REVOKED, "LEASE_REVOKED")


    def process_expirations(self) -> tuple[int, int]:
        """System sweep to process all expired leases. Returns (attempted, succeeded)."""
        now = datetime.now(timezone.utc)
        expired_leases = self._lease_repo.get_expired_active_leases(now)
        count = 0
        attempted = len(expired_leases)
        for lease in expired_leases:
            try:
                self.expire(lease.id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to expire lease {lease.id}: {e}")
        return attempted, count

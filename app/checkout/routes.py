"""Checkout API Routes."""

import logging
import uuid
from uuid import UUID

from flask import Blueprint, jsonify, request, g

from app.checkout.exceptions import CheckoutError
from app.checkout.repository import CredentialLeaseRepository
from app.checkout.service import CheckoutService
from app.platform.extensions import db
from app.authorization.service import AuthorizationService
from app.identity.repository import IdentityRepository
from app.auth.service import AuthService
from app.audit.service import AuditService
from app.audit.repository import AuditRepository
from app.access_requests.repository import AccessRequestRepository
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault.kms_factory import KMSProviderFactory
from app.vault.crypto import EncryptionService
from app.api.decorators import login_required

logger = logging.getLogger(__name__)
bp = Blueprint("checkout", __name__, url_prefix="/api/v1/checkout")


def get_checkout_service() -> CheckoutService:
    lease_repo = CredentialLeaseRepository(db.session)
    vault_repo = SqlAlchemyVaultRepository(db.session)
    policy_repo = SecretRotationPolicyRepository(db.session)
    ar_repo = AccessRequestRepository(db.session)
    audit_repo = AuditRepository(db.session)
    audit_service = AuditService(audit_repo)
    kms_provider = KMSProviderFactory.resolve_active_provider(db.session)
    encryption_service = EncryptionService(kms_provider)
    identity_repo = IdentityRepository(db.session)
    auth_service = AuthorizationService(identity_repo)

    return CheckoutService(
        session=db.session,
        lease_repo=lease_repo,
        vault_repo=vault_repo,
        policy_repo=policy_repo,
        ar_repo=ar_repo,
        audit_service=audit_service,
        authz_service=auth_service,
        encryption_service=encryption_service,
    )


@bp.route("/<uuid:access_request_id>", methods=["POST"])
@login_required
def checkout_credential(access_request_id: UUID):
    """Checkout a credential based on an approved access request."""
    user_id = uuid.UUID(g.user_id)
    service = get_checkout_service()

    try:
        plaintext = service.checkout(user_id, access_request_id)
        # Note: Plaintext is returned once here. Do not log it.
        return jsonify({
            "message": "Checkout successful",
            "credential": plaintext.decode("utf-8")
        }), 200
    except CheckoutError as e:
        return jsonify({"success": False, "message": "Bad Request", "errors": [str(e)]}), 400
    except Exception as e:
        logger.exception("Checkout failed")
        return jsonify({"success": False, "message": "Bad Request", "errors": ["Checkout failed due to an unexpected error."]}), 400


@bp.route("/checkin/<uuid:lease_id>", methods=["POST"])
@login_required
def checkin_credential(lease_id: UUID):
    """Check-in an actively leased credential."""
    user_id = uuid.UUID(g.user_id)
    service = get_checkout_service()

    try:
        service.checkin(user_id, lease_id)
        return jsonify({"message": "Check-in successful"}), 200
    except CheckoutError as e:
        return jsonify({"success": False, "message": "Bad Request", "errors": [str(e)]}), 400
    except Exception as e:
        logger.exception("Check-in failed")
        return jsonify({"success": False, "message": "Bad Request", "errors": ["Check-in failed due to an unexpected error."]}), 400


@bp.route("/leases/<uuid:lease_id>/revoke", methods=["POST"])
@login_required
def revoke_lease(lease_id: UUID):
    """Revoke an active lease (Admin only)."""
    admin_id = uuid.UUID(g.user_id)
    service = get_checkout_service()

    try:
        service.revoke(admin_id, lease_id)
        return jsonify({"message": "Lease revoked"}), 200
    except CheckoutError as e:
        return jsonify({"success": False, "message": "Bad Request", "errors": [str(e)]}), 400
    except Exception as e:
        logger.exception("Lease revocation failed")
        return jsonify({"success": False, "message": "Bad Request", "errors": ["Revocation failed due to an unexpected error."]}), 400

@bp.route("/expirations", methods=["POST"])
@login_required
def process_expirations():
    """System endpoint to process expired leases."""
    # In a real system, this would be locked down to a worker or admin
    service = get_checkout_service()
    
    try:
        count = service.process_expirations()
        return jsonify({"message": f"Processed {count} expirations"}), 200
    except Exception as e:
        logger.exception("Expiration processing failed")
        return jsonify({"success": False, "message": "Bad Request", "errors": ["Expiration processing failed."]}), 400


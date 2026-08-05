"""OpsForge Policy Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.authorization.service import AuthorizationService
from app.policy_engine.decisions import PolicyDecision
from app.resources.models import ResourceAccessPolicy


class PolicyEngine:
    """Platform Policy Engine to evaluate operation decisions."""

    def __init__(self, session: Session, authz_service: AuthorizationService) -> None:
        self._session = session
        self._authz = authz_service

    def evaluate_vault_retrieval(self, user_id: UUID, resource_id: UUID) -> PolicyDecision:
        """Evaluate if the user can retrieve secrets for the given resource."""

        # 1. Gather all roles for the user
        roles = self._authz.get_user_roles(user_id)
        if not roles:
            return PolicyDecision.DENY

        role_ids = [r.id for r in roles]

        # 2. Check if any ResourceAccessPolicy applies to these roles for the resource
        stmt = (
            select(ResourceAccessPolicy)
            .where(
                ResourceAccessPolicy.resource_id == resource_id,
                ResourceAccessPolicy.role_id.in_(role_ids)
            )
        )
        policies = self._session.execute(stmt).scalars().all()

        if not policies:
            # Check if there is an active APPROVED access request directly for this resource
            direct_ar_stmt = (
                select(AccessRequest)
                .where(
                    AccessRequest.requester_id == user_id,
                    AccessRequest.requested_resource_id == resource_id,
                    AccessRequest.status == AccessRequestStatus.APPROVED,
                )
            )
            direct_ars = self._session.execute(direct_ar_stmt).scalars().all()

            # Verify time window for the direct AR
            now = datetime.now(timezone.utc)
            valid_direct_ar = False
            for ar in direct_ars:
                start_ok = not ar.requested_start or ar.requested_start <= now
                end_ok = not ar.requested_end or ar.requested_end >= now
                if start_ok and end_ok:
                    valid_direct_ar = True
                    break

            if valid_direct_ar:
                return PolicyDecision.ALLOW

            return PolicyDecision.DENY

        # 3. Evaluate the policies
        # If any policy allows without approval, we can ALLOW.
        # If all applicable policies require approval, check for an active AccessRequest.
        requires_approval = True
        for policy in policies:
            if not policy.approval_required:
                requires_approval = False
                break

        if not requires_approval:
            return PolicyDecision.ALLOW

        # 4. Check for active approved access requests
        ar_stmt = (
            select(AccessRequest)
            .where(
                AccessRequest.requester_id == user_id,
                AccessRequest.requested_resource_id == resource_id,
                AccessRequest.status == AccessRequestStatus.APPROVED,
            )
        )
        approved_requests = self._session.execute(ar_stmt).scalars().all()

        now = datetime.now(timezone.utc)
        for ar in approved_requests:
            start_ok = not ar.requested_start or ar.requested_start <= now
            end_ok = not ar.requested_end or ar.requested_end >= now
            if start_ok and end_ok:
                return PolicyDecision.ALLOW

        return PolicyDecision.REQUIRE_APPROVAL

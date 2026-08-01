"""AccessRequest Service for OpsForge."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from app.access_requests.exceptions import (
    AccessRequestDuplicateError,
    AccessRequestInvalidStateError,
    AccessRequestValidationError,
)
from app.access_requests.models import (
    AccessRequest,
    AccessRequestPriority,
    AccessRequestStatus,
)
from app.access_requests.repository import AccessRequestRepository
from app.identity.repository import IdentityRepository
from app.notifications.events import (
    access_request_created,
    request_approved,
    request_cancelled,
    request_rejected,
)
from app.resources.repository import ResourcesRepository
from app.roles.repository import RolesRepository


class AccessRequestService:
    def __init__(
        self,
        access_request_repo: AccessRequestRepository,
        user_repo: IdentityRepository,
        role_repo: RolesRepository,
        resource_repo: ResourcesRepository,
        user_roles_repo: Any = None,
        # Avoid circular imports if needed, but we can type it properly if imported
    ) -> None:
        self._repo = access_request_repo
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._resource_repo = resource_repo
        self._user_roles_repo = user_roles_repo

    def submit_request(
        self,
        requester_id: UUID,
        business_justification: str,
        requested_role_id: UUID | None = None,
        requested_resource_id: UUID | None = None,
        priority: AccessRequestPriority = AccessRequestPriority.LOW,
        requested_start: datetime | None = None,
        requested_end: datetime | None = None,
    ) -> AccessRequest:

        # Validation
        if not requested_role_id and not requested_resource_id:
            raise AccessRequestValidationError(
                "Must specify either a role or a resource."
            )
        if requested_start and requested_end and requested_start >= requested_end:
            raise AccessRequestValidationError(
                "Requested start must be before requested end."
            )

        if not self._user_repo.get_by_id(requester_id):
            raise AccessRequestValidationError("Requester not found.")

        if requested_role_id:
            if not self._role_repo.get_by_id(requested_role_id):
                raise AccessRequestValidationError("Requested role not found.")

        if requested_resource_id:
            if not self._resource_repo.get_by_id(requested_resource_id):
                raise AccessRequestValidationError("Requested resource not found.")

        # Prevent duplicate active requests
        active_count = self._repo.count(
            requester_id=requester_id,
            requested_role_id=requested_role_id,
            requested_resource_id=requested_resource_id,
            status=AccessRequestStatus.PENDING,
        )
        if active_count > 0:
            raise AccessRequestDuplicateError("An active request already exists.")

        request_number = f"REQ-{uuid.uuid4().hex[:8].upper()}"

        req = AccessRequest(
            request_number=request_number,
            requester_id=requester_id,
            requested_role_id=requested_role_id,
            requested_resource_id=requested_resource_id,
            business_justification=business_justification,
            priority=priority,
            requested_start=requested_start,
            requested_end=requested_end,
            status=AccessRequestStatus.PENDING,
        )
        created = self._repo.create_request(req)

        access_request_created.send(
            self,
            payload={
                "event": "access_request_created",
                "request_id": str(created.id),
                "actor_id": str(requester_id),
                "recipient_id": str(
                    requester_id
                ),  # Usually we notify the requester, but wait, who should be notified?
                # The prompt says: "Automatically generate notifications for: Access
                # Request Created -> User receives notification"
                "title": "Access Request Created",
                "message": f"Your access request {request_number} has been submitted.",
                "type": "access_request_created",
                "priority": "normal",
            },
        )
        return created

    def approve_request(self, request_id: UUID, approver_id: UUID) -> AccessRequest:
        req = self._repo.get_by_id(request_id)
        if not req:
            raise AccessRequestValidationError("Access request not found.")
        if req.status != AccessRequestStatus.PENDING:
            raise AccessRequestInvalidStateError(
                "Only pending requests can be approved."
            )

        # Provision the requested access first
        if req.requested_role_id and self._user_roles_repo:
            from app.user_roles.exceptions import UserRoleAlreadyExistsError

            try:
                self._user_roles_repo.assign_role_to_user(
                    req.requester_id, req.requested_role_id, approver_id
                )
            except UserRoleAlreadyExistsError:
                pass  # If they already have it, just mark request approved

        approved_req = self._repo.approve(request_id, approver_id)

        request_approved.send(
            self,
            payload={
                "event": "request_approved",
                "request_id": str(approved_req.id),
                "actor_id": str(approver_id),
                "recipient_id": str(approved_req.requester_id),
                "title": "Access Request Approved",
                "message": f"Your access request {approved_req.request_number} has been approved.",
                "type": "request_approved",
                "priority": "high",
            },
        )
        return approved_req

    def reject_request(
        self, request_id: UUID, reason: str, rejecter_id: UUID | None = None
    ) -> AccessRequest:
        req = self._repo.get_by_id(request_id)
        if not req:
            raise AccessRequestValidationError("Access request not found.")
        if req.status != AccessRequestStatus.PENDING:
            raise AccessRequestInvalidStateError(
                "Only pending requests can be rejected."
            )
        rejected_req = self._repo.reject(request_id, reason, rejecter_id)

        request_rejected.send(
            self,
            payload={
                "event": "request_rejected",
                "request_id": str(rejected_req.id),
                "actor_id": str(rejecter_id) if rejecter_id else "system",
                "recipient_id": str(rejected_req.requester_id),
                "title": "Access Request Rejected",
                "message": f"Your access request {rejected_req.request_number} has been rejected.",
                "type": "request_rejected",
                "priority": "high",
            },
        )
        return rejected_req

    def cancel_request(self, request_id: UUID) -> AccessRequest:
        req = self._repo.get_by_id(request_id)
        if not req:
            raise AccessRequestValidationError("Access request not found.")
        if req.status not in (
            AccessRequestStatus.PENDING,
            AccessRequestStatus.APPROVED,
        ):
            raise AccessRequestInvalidStateError("Request cannot be cancelled.")
        cancelled_req = self._repo.cancel(request_id)

        request_cancelled.send(
            self,
            payload={
                "event": "request_cancelled",
                "request_id": str(cancelled_req.id),
                "recipient_id": str(cancelled_req.requester_id),
                "title": "Access Request Cancelled",
                "message": f"Your access request {cancelled_req.request_number} has been cancelled.",
                "type": "request_cancelled",
                "priority": "normal",
            },
        )
        return cancelled_req


__all__ = ["AccessRequestService"]

import uuid
from datetime import datetime, timezone
import pytest

from app.access_requests.exceptions import (
    AccessRequestDuplicateError,
    AccessRequestInvalidStateError,
    AccessRequestValidationError,
)
from app.access_requests.models import AccessRequestPriority, AccessRequestStatus


def test_submit_valid_role_request(ar_service, normal_user, sample_role):
    """Test submitting a valid access request for a role."""
    req = ar_service.submit_request(
        requester_id=normal_user.id,
        business_justification="Need admin access for deployment",
        requested_role_id=sample_role.id,
        priority=AccessRequestPriority.HIGH,
    )
    assert req.id is not None
    assert req.request_number.startswith("REQ-")
    assert req.status == AccessRequestStatus.PENDING
    assert req.business_justification == "Need admin access for deployment"
    assert req.priority == AccessRequestPriority.HIGH


def test_submit_duplicate_request_raises_error(ar_service, normal_user, sample_role):
    """Test that submitting a duplicate active request raises an error."""
    # First request
    ar_service.submit_request(
        requester_id=normal_user.id,
        business_justification="First request",
        requested_role_id=sample_role.id,
    )

    # Second request for the same role should fail
    with pytest.raises(AccessRequestDuplicateError, match="An active request already exists"):
        ar_service.submit_request(
            requester_id=normal_user.id,
            business_justification="Second request",
            requested_role_id=sample_role.id,
        )


def test_cancel_request_success(ar_service, normal_user, sample_role):
    req = ar_service.submit_request(normal_user.id, "Test", requested_role_id=sample_role.id)
    cancelled_req = ar_service.cancel_request(req.id)
    assert cancelled_req.status == AccessRequestStatus.CANCELLED


def test_approve_request_success(ar_service, normal_user, sample_role, db_session, admin_user):
    """Test approving a pending access request and verifying role assignment."""
    req = ar_service.submit_request(normal_user.id, "Test", requested_role_id=sample_role.id)
    admin = admin_user
    
    # Must use actual user with a valid role (if we're assigning one)
    db_session.commit()

    approved_req = ar_service.approve_request(req.id, approver_id=admin.id)
    assert approved_req.status == AccessRequestStatus.APPROVED
    assert approved_req.approved_by == admin.id
    assert approved_req.approved_at is not None

    # Verify role was assigned
    from app.roles.models import UserRole
    ur = db_session.query(UserRole).filter_by(user_id=req.requester_id, role_id=sample_role.id).first()
    assert ur is not None


def test_reject_request_success(ar_service, normal_user, sample_role, db_session, admin_user):
    """Test rejecting a pending access request."""
    req = ar_service.submit_request(normal_user.id, "Test", requested_role_id=sample_role.id)
    admin = admin_user

    rejected_req = ar_service.reject_request(
        req.id,
        reason="Insufficient justification",
        rejecter_id=admin.id
    )
    assert rejected_req.status == AccessRequestStatus.REJECTED
    assert rejected_req.rejected_reason == "Insufficient justification"


def test_search_access_requests(ar_service, normal_user, sample_role):
    """Test searching access requests by text."""
    req1 = ar_service.submit_request(
        requester_id=normal_user.id,
        business_justification="Need access for Project Alpha deployment",
        requested_role_id=sample_role.id,
    )
    
    # Needs a different user or role to avoid duplicate constraint if they are both pending, 
    # but duplicate checks requested_role_id. We'll use a different resource.
    from app.resources.models import Resource, ResourceType
    from app.shared.database import db
    res = Resource(resource_code="RES_BETA", resource_name="Beta", resource_type=ResourceType.APPLICATION)
    db.session.add(res)
    db.session.commit()
    
    req2 = ar_service.submit_request(
        requester_id=normal_user.id,
        business_justification="Need access for Project Beta database",
        requested_resource_id=res.id,
    )
    
    # Search for Alpha
    results = ar_service._repo.search(search="Alpha")
    assert len(results) == 1
    assert results[0].id == req1.id

    # Search for Beta
    results2 = ar_service._repo.search(search="Beta")
    assert len(results2) == 1
    assert results2[0].id == req2.id
    
    # Search by request number
    results3 = ar_service._repo.search(search=req1.request_number)
    assert len(results3) == 1
    assert results3[0].id == req1.id

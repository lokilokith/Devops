import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.access_requests.models import AccessRequestStatus, AccessRequestPriority
from app.access_requests.exceptions import (
    AccessRequestInvalidStateError,
    AccessRequestDuplicateError,
    AccessRequestValidationError,
)

def test_submit_request(ar_service, sample_user, sample_role, sample_resource):
    # Role request
    req1 = ar_service.submit_request(
        requester_id=sample_user.id,
        business_justification="Test role",
        requested_role_id=sample_role.id
    )
    assert req1.status == AccessRequestStatus.PENDING
    assert req1.requested_role_id == sample_role.id
    
    # Resource request
    req2 = ar_service.submit_request(
        requester_id=sample_user.id,
        business_justification="Test resource",
        requested_resource_id=sample_resource.id,
        priority=AccessRequestPriority.HIGH
    )
    assert req2.status == AccessRequestStatus.PENDING
    assert req2.requested_resource_id == sample_resource.id

def test_submit_request_validations(ar_service, sample_user, sample_role):
    # Missing role and resource
    with pytest.raises(AccessRequestValidationError, match="Must specify either a role or a resource"):
        ar_service.submit_request(sample_user.id, "Test")

    # Start >= End
    start = datetime.now(timezone.utc)
    end = start - timedelta(days=1)
    with pytest.raises(AccessRequestValidationError, match="start must be before requested end"):
        ar_service.submit_request(sample_user.id, "Test", requested_role_id=sample_role.id, requested_start=start, requested_end=end)

    # Unknown user
    with pytest.raises(AccessRequestValidationError, match="Requester not found"):
        ar_service.submit_request(uuid4(), "Test", requested_role_id=sample_role.id)

    # Unknown role
    with pytest.raises(AccessRequestValidationError, match="Requested role not found"):
        ar_service.submit_request(sample_user.id, "Test", requested_role_id=uuid4())

    # Unknown resource
    with pytest.raises(AccessRequestValidationError, match="Requested resource not found"):
        ar_service.submit_request(sample_user.id, "Test", requested_resource_id=uuid4())

def test_duplicate_request(ar_service, sample_user, sample_role):
    ar_service.submit_request(sample_user.id, "Test", requested_role_id=sample_role.id)
    with pytest.raises(AccessRequestDuplicateError):
        ar_service.submit_request(sample_user.id, "Test again", requested_role_id=sample_role.id)



def test_approve_request(ar_service, sample_user, sample_role, db_session):
    from app.resources.models import Resource, ResourceType, ResourceStatus
    res1 = Resource(resource_code="TRES1", resource_name="Res1", resource_type=ResourceType.SERVER, status=ResourceStatus.ACTIVE)
    db_session.add(res1)
    db_session.commit()

    req1 = ar_service.submit_request(sample_user.id, "T1", requested_role_id=sample_role.id)
    approved = ar_service.approve_request(req1.id, sample_user.id)
    assert approved.status == AccessRequestStatus.APPROVED

    with pytest.raises(AccessRequestInvalidStateError):
        ar_service.approve_request(req1.id, sample_user.id)

def test_reject_request(ar_service, sample_user, sample_role, db_session):
    from app.resources.models import Resource, ResourceType, ResourceStatus
    res2 = Resource(resource_code="TRES2", resource_name="Res2", resource_type=ResourceType.SERVER, status=ResourceStatus.ACTIVE)
    db_session.add(res2)
    db_session.commit()

    req2 = ar_service.submit_request(sample_user.id, "T2", requested_resource_id=res2.id)
    rejected = ar_service.reject_request(req2.id, "No.")
    assert rejected.status == AccessRequestStatus.REJECTED

    with pytest.raises(AccessRequestInvalidStateError):
        ar_service.reject_request(req2.id, "No.")

def test_cancel_request(ar_service, sample_user, sample_role, db_session):
    from app.resources.models import Resource, ResourceType, ResourceStatus
    res3 = Resource(resource_code="TRES3", resource_name="Res3", resource_type=ResourceType.SERVER, status=ResourceStatus.ACTIVE)
    db_session.add(res3)
    db_session.commit()

    req3 = ar_service.submit_request(sample_user.id, "T3", requested_resource_id=res3.id)
    cancelled = ar_service.cancel_request(req3.id)
    assert cancelled.status == AccessRequestStatus.CANCELLED

    with pytest.raises(AccessRequestInvalidStateError):
        ar_service.cancel_request(req3.id)

def test_service_not_found(ar_service, sample_user):
    with pytest.raises(AccessRequestValidationError, match="Access request not found"):
        ar_service.approve_request(uuid4(), sample_user.id)
    with pytest.raises(AccessRequestValidationError, match="Access request not found"):
        ar_service.reject_request(uuid4(), "test")
    with pytest.raises(AccessRequestValidationError, match="Access request not found"):
        ar_service.cancel_request(uuid4())

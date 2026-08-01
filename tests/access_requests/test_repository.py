from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.access_requests.exceptions import (
    AccessRequestNotFoundError,
    AccessRequestRepositoryError,
)
from app.access_requests.models import (
    AccessRequest,
    AccessRequestPriority,
    AccessRequestStatus,
)


def test_create_and_get(ar_repo, sample_user, sample_role):
    req = AccessRequest(
        request_number="REQ-123456",
        requester_id=sample_user.id,
        requested_role_id=sample_role.id,
        business_justification="Need access.",
        status=AccessRequestStatus.PENDING,
        priority=AccessRequestPriority.LOW,
    )
    created = ar_repo.create_request(req)
    assert created.id is not None

    fetched = ar_repo.get_by_id(created.id)
    assert fetched.request_number == "REQ-123456"

    fetched_num = ar_repo.get_by_request_number("REQ-123456")
    assert fetched_num.id == created.id


def test_update_status(ar_repo, sample_user, sample_role):
    req = AccessRequest(
        request_number="REQ-2",
        requester_id=sample_user.id,
        requested_role_id=sample_role.id,
        business_justification="Need access.",
        status=AccessRequestStatus.PENDING,
        priority=AccessRequestPriority.LOW,
    )
    created = ar_repo.create_request(req)
    updated = ar_repo.update_status(created.id, AccessRequestStatus.REJECTED)
    assert updated.status == AccessRequestStatus.REJECTED


def test_approve_reject_cancel(ar_repo, sample_user, sample_role):
    req1 = ar_repo.create_request(
        AccessRequest(
            request_number="REQ-A1",
            requester_id=sample_user.id,
            requested_role_id=sample_role.id,
            business_justification="Test",
        )
    )
    approved = ar_repo.approve(req1.id, sample_user.id)
    assert approved.status == AccessRequestStatus.APPROVED
    assert approved.approved_by == sample_user.id
    assert approved.approved_at is not None

    req2 = ar_repo.create_request(
        AccessRequest(
            request_number="REQ-A2",
            requester_id=sample_user.id,
            requested_role_id=sample_role.id,
            business_justification="Test",
        )
    )
    rejected = ar_repo.reject(req2.id, "No.")
    assert rejected.status == AccessRequestStatus.REJECTED
    assert rejected.rejected_reason == "No."

    req3 = ar_repo.create_request(
        AccessRequest(
            request_number="REQ-A3",
            requester_id=sample_user.id,
            requested_role_id=sample_role.id,
            business_justification="Test",
        )
    )
    cancelled = ar_repo.cancel(req3.id)
    assert cancelled.status == AccessRequestStatus.CANCELLED


def test_list_and_count_and_search(ar_repo, sample_user, sample_role, sample_resource):
    ar_repo.create_request(
        AccessRequest(
            request_number="REQ-L1",
            requester_id=sample_user.id,
            requested_role_id=sample_role.id,
            business_justification="Test",
        )
    )
    ar_repo.create_request(
        AccessRequest(
            request_number="REQ-L2",
            requester_id=sample_user.id,
            requested_resource_id=sample_resource.id,
            business_justification="Test",
            status=AccessRequestStatus.APPROVED,
        )
    )

    assert ar_repo.count() >= 2
    assert ar_repo.count(status=AccessRequestStatus.APPROVED) >= 1
    assert ar_repo.count(requested_role_id=sample_role.id) >= 1

    lst = ar_repo.list_requests()
    assert len(lst) >= 2

    srch = ar_repo.search(requested_resource_id=sample_resource.id)
    assert len(srch) == 1
    assert srch[0].request_number == "REQ-L2"


def test_not_found(ar_repo):
    with pytest.raises(AccessRequestNotFoundError):
        ar_repo.update_status(uuid4(), AccessRequestStatus.APPROVED)
    with pytest.raises(AccessRequestNotFoundError):
        ar_repo.approve(uuid4(), uuid4())
    with pytest.raises(AccessRequestNotFoundError):
        ar_repo.reject(uuid4(), "test")


def test_sqlalchemy_errors(ar_repo, sample_user, sample_role):
    req = AccessRequest(
        request_number="REQ-ERR",
        requester_id=sample_user.id,
        requested_role_id=sample_role.id,
        business_justification="Need access.",
    )

    with patch.object(
        ar_repo._session, "add", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.create_request(req)

    with patch.object(
        ar_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.get_by_id(uuid4())

    with patch.object(
        ar_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.get_by_request_number("mock")

    with patch.object(
        ar_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.list_requests()

    with patch.object(
        ar_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.count()

    with patch.object(
        ar_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.search()

    req2 = ar_repo.create_request(
        AccessRequest(
            request_number="REQ-ERR2",
            requester_id=sample_user.id,
            requested_role_id=sample_role.id,
            business_justification="Test",
        )
    )

    with patch.object(
        ar_repo._session, "commit", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.update_status(req2.id, AccessRequestStatus.REJECTED)

    with patch.object(
        ar_repo._session, "commit", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.approve(req2.id, sample_user.id)

    with patch.object(
        ar_repo._session, "commit", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AccessRequestRepositoryError):
            ar_repo.reject(req2.id, "No.")

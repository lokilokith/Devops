"""Tests for JITAccessRepository."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.jit_access.exceptions import GrantNotFoundError
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from tests.fixtures.factories import (
    AccessRequestFactory,
    ResourceFactory,
    RoleFactory,
    UserFactory,
)


def test_create_grant(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    created = JITAccessRepository.create(grant)
    assert created.id is not None
    assert created.status == JITGrantStatus.PENDING


def test_get_by_id(db_session):
    grant = JITAccessGrant(
        user_id=uuid4(),
        role_id=uuid4(),
        resource_id=uuid4(),
        approval_request_id=uuid4(),
        expires_at=datetime.now(timezone.utc),
    )
    # We must ensure FK constraints are met if we use uuid4, but SQLite might ignore them.
    # Postgres will enforce them, so we must use actual IDs.
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant.user_id = user.id
    grant.role_id = role.id
    grant.resource_id = resource.id
    grant.approval_request_id = ar.id

    created = JITAccessRepository.create(grant)

    fetched = JITAccessRepository.get_by_id(created.id)
    assert fetched.id == created.id


def test_get_by_id_not_found(db_session):
    with pytest.raises(GrantNotFoundError):
        JITAccessRepository.get_by_id(uuid4())


def test_get_by_approval_request(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        expires_at=datetime.now(timezone.utc),
    )
    JITAccessRepository.create(grant)

    fetched = JITAccessRepository.get_by_approval_request(ar.id)
    assert fetched.approval_request_id == ar.id


def test_update_grant(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc),
    )
    created = JITAccessRepository.create(grant)

    created.status = JITGrantStatus.ACTIVE
    updated = JITAccessRepository.update(created)
    assert updated.status == JITGrantStatus.ACTIVE


def test_list_grants(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant1 = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc),
    )
    grant2 = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=uuid4(),
        status=JITGrantStatus.PENDING,
        expires_at=datetime.now(timezone.utc),
    )
    # create second AR properly
    ar2 = AccessRequestFactory()
    db_session.add(ar2)
    db_session.flush()
    grant2.approval_request_id = ar2.id

    JITAccessRepository.create(grant1)
    JITAccessRepository.create(grant2)

    grants, total = JITAccessRepository.list_grants(user_id=user.id)
    assert total >= 2

    grants, total = JITAccessRepository.list_grants(status=JITGrantStatus.ACTIVE)
    assert total >= 1


def test_check_active_grant_true(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    JITAccessRepository.create(grant)

    is_active = JITAccessRepository.check_active_grant(user.id, role.id, resource.id)
    assert is_active is True


def test_check_active_grant_expired(db_session):
    user = UserFactory()
    role = RoleFactory()
    resource = ResourceFactory()
    ar = AccessRequestFactory()
    db_session.add_all([user, role, resource, ar])
    db_session.flush()

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        approval_request_id=ar.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    JITAccessRepository.create(grant)

    is_active = JITAccessRepository.check_active_grant(user.id, role.id, resource.id)
    assert is_active is False

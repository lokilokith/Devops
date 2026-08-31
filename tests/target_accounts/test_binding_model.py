"""Tests for TargetAccountBinding domain model and database constraints."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.identity.models import User, UserStatus
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.target_accounts.models import (
    TargetAccountBinding,
    TargetAccountBindingStatus,
)


def _create_user(db_session, username="alice"):
    u = User(
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        username=f"{username}_{uuid.uuid4().hex[:6]}",
        email=f"{username}_{uuid.uuid4().hex[:6]}@example.com",
        full_name=f"Test {username}",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _create_resource(db_session):
    r = Resource(
        resource_code=f"srv_{uuid.uuid4().hex[:6]}",
        resource_name=f"Server {uuid.uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
    )
    db_session.add(r)
    db_session.commit()
    return r


def test_target_account_binding_creation(db_session):
    """Test standard TargetAccountBinding creation with PENDING default."""
    user = _create_user(db_session, "testuser")
    res = _create_resource(db_session)

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res.id,
        target_os_username="testuser",
        status=TargetAccountBindingStatus.PENDING,
    )
    db_session.add(binding)
    db_session.commit()

    assert binding.id is not None
    assert binding.status == TargetAccountBindingStatus.PENDING
    assert binding.row_version == 1


def test_duplicate_user_resource_binding_rejected(db_session):
    """Invariant 1: A Control Plane user may have at most one target account per Resource."""
    user = _create_user(db_session, "dupuser")
    res = _create_resource(db_session)

    binding1 = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res.id,
        target_os_username="dupuser_1",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding1)
    db_session.commit()

    binding2 = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res.id,
        target_os_username="dupuser_2",
        status=TargetAccountBindingStatus.PENDING,
    )
    db_session.add(binding2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_os_username_on_same_resource_rejected(db_session):
    """Invariant 2: Two different Control Plane users must NEVER share the same target OS account."""
    user1 = _create_user(db_session, "user1")
    user2 = _create_user(db_session, "user2")
    res = _create_resource(db_session)

    binding1 = TargetAccountBinding(
        control_plane_user_id=user1.id,
        resource_id=res.id,
        target_os_username="shared_os_user",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding1)
    db_session.commit()

    binding2 = TargetAccountBinding(
        control_plane_user_id=user2.id,
        resource_id=res.id,
        target_os_username="shared_os_user",
        status=TargetAccountBindingStatus.PENDING,
    )
    db_session.add(binding2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_binding_lifecycle_transitions(db_session):
    """Test state progression: PENDING -> ACTIVE -> SUSPENDED -> REMOVED."""
    user = _create_user(db_session, "lifecycle")
    res = _create_resource(db_session)

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=res.id,
        target_os_username="lifecycle",
        status=TargetAccountBindingStatus.PENDING,
    )
    db_session.add(binding)
    db_session.commit()
    assert binding.status == TargetAccountBindingStatus.PENDING

    # Transition to ACTIVE
    binding.status = TargetAccountBindingStatus.ACTIVE
    db_session.commit()
    assert binding.status == TargetAccountBindingStatus.ACTIVE

    # Transition to SUSPENDED
    binding.status = TargetAccountBindingStatus.SUSPENDED
    db_session.commit()
    assert binding.status == TargetAccountBindingStatus.SUSPENDED

    # Transition to REMOVED
    binding.status = TargetAccountBindingStatus.REMOVED
    db_session.commit()
    assert binding.status == TargetAccountBindingStatus.REMOVED

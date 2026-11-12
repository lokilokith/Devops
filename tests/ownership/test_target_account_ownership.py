"""Ownership and Authorization tests for TargetAccountBindings."""

import uuid

from app.identity.models import User, UserStatus
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.target_accounts.models import (
    TargetAccountBinding,
    TargetAccountBindingStatus,
)
from app.target_accounts.repository import TargetAccountBindingRepository


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


def test_user_ownership_isolation(db_session):
    """Test user A sees only user A's bindings, user B sees only user B's bindings."""
    user_a = _create_user(db_session, "user_a")
    user_b = _create_user(db_session, "user_b")
    res = _create_resource(db_session)

    repo = TargetAccountBindingRepository(db_session)

    binding_a = TargetAccountBinding(
        control_plane_user_id=user_a.id,
        resource_id=res.id,
        target_os_username="user_a",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    binding_b = TargetAccountBinding(
        control_plane_user_id=user_b.id,
        resource_id=res.id,
        target_os_username="user_b",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    repo.create(binding_a)
    repo.create(binding_b)
    db_session.commit()

    # User A listing
    a_bindings = repo.list_by_user(user_a.id)
    assert len(a_bindings) == 1
    assert a_bindings[0].id == binding_a.id

    # User B listing
    b_bindings = repo.list_by_user(user_b.id)
    assert len(b_bindings) == 1
    assert b_bindings[0].id == binding_b.id

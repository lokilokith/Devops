"""Tests for Policy Engine Repository."""

from uuid import uuid4

import pytest

from app.policy_engine.exceptions import PolicyNotFoundError
from app.policy_engine.models import AccessPolicy, PolicyEffect
from app.policy_engine.repository import PolicyRepository


def test_create_and_get_policy(db_session):
    repo = PolicyRepository(db_session)
    policy = AccessPolicy(
        name="Test Policy",
        conditions={"allowed_ip_ranges": ["10.0.0.0/8"]},
        effect=PolicyEffect.ALLOW,
        priority=10,
    )
    repo.create(policy)

    retrieved = repo.get_by_id(policy.id)
    assert retrieved is not None
    assert retrieved.name == "Test Policy"
    assert retrieved.effect == PolicyEffect.ALLOW
    assert retrieved.priority == 10


def test_duplicate_name_fails(db_session):
    repo = PolicyRepository(db_session)
    policy1 = AccessPolicy(name="Unique Name", conditions={})
    repo.create(policy1)

    policy2 = AccessPolicy(name="Unique Name", conditions={})
    with pytest.raises(Exception):
        repo.create(policy2)


def test_list_and_count_policies(db_session):
    repo = PolicyRepository(db_session)
    repo.create(AccessPolicy(name="Policy A", conditions={}, priority=5, enabled=True))
    repo.create(AccessPolicy(name="Policy B", conditions={}, priority=15, enabled=True))
    repo.create(AccessPolicy(name="Policy C", conditions={}, priority=0, enabled=False))

    assert repo.count_policies() == 3
    assert repo.count_policies(enabled=True) == 2

    active = repo.get_active_policies()
    assert len(active) == 2
    # Ordered by priority desc
    assert active[0].name == "Policy B"
    assert active[1].name == "Policy A"


def test_update_policy(db_session):
    repo = PolicyRepository(db_session)
    policy = repo.create(AccessPolicy(name="Update Me", conditions={}))

    policy.priority = 99
    updated = repo.update(policy)

    assert updated.priority == 99

    fetched = repo.get_by_id(policy.id)
    assert fetched.priority == 99


def test_delete_policy(db_session):
    repo = PolicyRepository(db_session)
    policy = repo.create(AccessPolicy(name="Delete Me", conditions={}))

    assert repo.delete(policy.id) is True
    assert repo.get_by_id(policy.id) is None

    with pytest.raises(PolicyNotFoundError):
        repo.delete(uuid4())

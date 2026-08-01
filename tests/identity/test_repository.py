import uuid

import pytest

from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository, IdentityRepositoryError


def test_exists_by_employee_id(db_session):
    repo = IdentityRepository(db_session)
    user1 = User(
        employee_id="EMP-TEST-001",
        username="testuser1",
        email="testuser1@example.com",
        full_name="Test User 1",
    )
    user2 = User(
        employee_id="EMP-TEST-002",
        username="testuser2",
        email="testuser2@example.com",
        full_name="Test User 2",
    )
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()

    assert repo.exists_by_employee_id("EMP-TEST-001") is True
    assert repo.exists_by_employee_id("EMP-TEST-002") is True
    assert repo.exists_by_employee_id("EMP-MISSING") is False

    # test exclude logic
    assert repo.exists_by_employee_id("EMP-TEST-001", exclude_user_id=user1.id) is False
    assert repo.exists_by_employee_id("EMP-TEST-001", exclude_user_id=user2.id) is True


def test_search_users(db_session):
    repo = IdentityRepository(db_session)
    user1 = User(
        employee_id="SEARCH-01",
        username="alpha",
        email="alpha@test.com",
        full_name="Alpha Team",
    )
    user2 = User(
        employee_id="SEARCH-02",
        username="beta",
        email="beta@test.com",
        full_name="Beta Team",
    )
    user3 = User(
        employee_id="SEARCH-03",
        username="gamma",
        email="gamma@xyz.com",
        full_name="Gamma Squad",
    )
    db_session.add_all([user1, user2, user3])
    db_session.commit()

    # search by username
    results = repo.search_users("alpha")
    assert len(results) == 1
    assert results[0].username == "alpha"

    # search by full name
    results = repo.search_users("Team")
    assert len(results) == 2

    # search by email
    results = repo.search_users("xyz")
    assert len(results) == 1
    assert results[0].username == "gamma"


def test_count_users(db_session):
    repo = IdentityRepository(db_session)
    count_before = repo.count_users()

    user1 = User(
        employee_id="COUNT-01",
        username="count1",
        email="c1@test.com",
        full_name="Count 1",
    )
    user2 = User(
        employee_id="COUNT-02",
        username="count2",
        email="c2@test.com",
        full_name="Count 2",
    )
    db_session.add_all([user1, user2])
    db_session.commit()

    assert repo.count_users() == count_before + 2

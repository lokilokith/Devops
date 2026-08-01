from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.roles.exceptions import RoleNotFoundError, RolesRepositoryError
from app.roles.models import Role, RoleStatus, RoleType


def test_roles_repository_create_and_get(roles_repo):
    role = Role(
        role_code="ADM",
        role_name="Admin",
        role_type=RoleType.SYSTEM,
        description="Admin role",
        status=RoleStatus.ACTIVE,
    )
    created_role = roles_repo.create(role)
    assert created_role.id is not None
    assert created_role.role_code == "ADM"

    fetched_role = roles_repo.get_by_id(created_role.id)
    assert fetched_role is not None
    assert fetched_role.role_code == "ADM"


def test_roles_repository_get_by_code_and_name_whitespace(roles_repo, sample_role):
    r1 = roles_repo.get_by_role_code("  SMPL  ")
    assert r1 is not None
    assert r1.id == sample_role.id

    r2 = roles_repo.get_by_role_name("  Sample Role  ")
    assert r2 is not None
    assert r2.id == sample_role.id


def test_roles_repository_update(roles_repo, sample_role):
    sample_role.role_name = "Sample Role Updated"
    roles_repo.update(sample_role)

    fetched = roles_repo.get_by_id(sample_role.id)
    assert fetched.role_name == "Sample Role Updated"


def test_roles_repository_delete(roles_repo, sample_role):
    roles_repo.delete(sample_role.id)

    fetched = roles_repo.get_by_id(sample_role.id)
    assert fetched is None


def test_roles_repository_status_changes(roles_repo, sample_role):
    roles_repo.deactivate(sample_role.id)
    assert roles_repo.get_by_id(sample_role.id).status == RoleStatus.INACTIVE

    roles_repo.retire(sample_role.id)
    assert roles_repo.get_by_id(sample_role.id).status == RoleStatus.RETIRED

    roles_repo.activate(sample_role.id)
    assert roles_repo.get_by_id(sample_role.id).status == RoleStatus.ACTIVE


def test_roles_repository_list_filters(roles_repo, sample_role):
    role2 = Role(
        role_code="LST2",
        role_name="List 2",
        role_type=RoleType.CUSTOM,
        status=RoleStatus.INACTIVE,
    )
    roles_repo.create(role2)

    roles_all = roles_repo.list()
    assert len(roles_all) >= 2

    roles_active = roles_repo.list(status=RoleStatus.ACTIVE)
    assert any(r.role_code == "SMPL" for r in roles_active)
    assert all(r.status == RoleStatus.ACTIVE for r in roles_active)

    roles_system = roles_repo.list(role_type=RoleType.SYSTEM)
    assert any(r.role_code == "SMPL" for r in roles_system)
    assert all(r.role_type == RoleType.SYSTEM for r in roles_system)

    roles_combo = roles_repo.list(status=RoleStatus.INACTIVE, role_type=RoleType.CUSTOM)
    assert len(roles_combo) >= 1
    assert any(r.role_code == "LST2" for r in roles_combo)


def test_roles_repository_count_filters(roles_repo, sample_role):
    role2 = Role(
        role_code="CNT2",
        role_name="Count 2",
        role_type=RoleType.CUSTOM,
        status=RoleStatus.INACTIVE,
    )
    roles_repo.create(role2)

    assert roles_repo.count() >= 2
    assert roles_repo.count(status=RoleStatus.INACTIVE) >= 1
    assert roles_repo.count(role_type=RoleType.CUSTOM) >= 1
    assert roles_repo.count(status=RoleStatus.INACTIVE, role_type=RoleType.CUSTOM) >= 1


def test_roles_repository_search_filters(roles_repo, sample_role):
    role2 = Role(
        role_code="SRCH2",
        role_name="Search Two",
        role_type=RoleType.CUSTOM,
        status=RoleStatus.INACTIVE,
    )
    roles_repo.create(role2)

    res1 = roles_repo.search(role_name="Search", role_code="SRCH")
    assert len(res1) == 1
    assert res1[0].role_code == "SRCH2"

    res2 = roles_repo.search(status=RoleStatus.INACTIVE)
    assert len(res2) >= 1
    assert any(r.role_code == "SRCH2" for r in res2)

    res3 = roles_repo.search(role_type=RoleType.CUSTOM)
    assert len(res3) >= 1
    assert any(r.role_code == "SRCH2" for r in res3)

    res4 = roles_repo.search(role_code="  SRCH2  ", role_name="  Two  ")
    assert len(res4) == 1
    assert res4[0].role_code == "SRCH2"


def test_roles_repository_exists_whitespace(roles_repo, sample_role):
    assert roles_repo.exists_by_role_code("  SMPL  ") is True
    assert roles_repo.exists_by_role_name("  Sample Role  ") is True
    assert roles_repo.exists_by_role_code("NONEXISTENT") is False
    assert roles_repo.exists_by_role_name("NONEXISTENT") is False


def test_roles_repository_pagination(roles_repo):
    roles_repo.create(Role(role_code="PAG1", role_name="Pag 1"))

    res1 = roles_repo.list(limit=0)
    assert len(res1) == 1

    res2 = roles_repo.list(limit=2000)
    assert len(res2) >= 1

    res3 = roles_repo.list(offset=-10)
    assert len(res3) >= 1


def test_roles_repository_not_found_errors(roles_repo):
    missing_id = uuid4()
    with pytest.raises(RoleNotFoundError):
        roles_repo.delete(missing_id)
    with pytest.raises(RoleNotFoundError):
        roles_repo.activate(missing_id)


def test_roles_repository_sqlalchemy_errors(roles_repo, sample_role):
    with patch.object(
        roles_repo._session, "add", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.create(Role(role_code="ERR", role_name="Error Role"))

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.get_by_id(sample_role.id)

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.get_by_role_code("SMPL")

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.get_by_role_name("Sample Role")

    with patch.object(
        roles_repo._session, "merge", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.update(sample_role)

    with patch.object(
        roles_repo._session, "delete", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.delete(sample_role.id)

    with patch.object(
        roles_repo._session, "commit", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.activate(sample_role.id)

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.exists_by_role_code("SMPL")

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.exists_by_role_name("Sample Role")

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.list()

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.count()

    with patch.object(
        roles_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(RolesRepositoryError):
            roles_repo.search()

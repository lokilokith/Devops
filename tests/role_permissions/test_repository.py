from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.role_permissions.exceptions import (
    RolePermissionAlreadyExistsError,
    RolePermissionNotFoundError,
    RolePermissionsRepositoryError,
)
from app.roles.models import Role, RoleStatus, RoleType


def test_assign_permission_to_role(
    role_permissions_repo, sample_role, sample_permission
):
    rp = role_permissions_repo.assign_permission_to_role(
        sample_role.id, sample_permission.id
    )
    assert rp.role_id == sample_role.id
    assert rp.permission_id == sample_permission.id
    assert role_permissions_repo.exists(sample_role.id, sample_permission.id) is True


def test_assign_permission_already_exists(
    role_permissions_repo, sample_role, sample_permission
):
    role_permissions_repo.assign_permission_to_role(
        sample_role.id, sample_permission.id
    )
    with pytest.raises(RolePermissionAlreadyExistsError):
        role_permissions_repo.assign_permission_to_role(
            sample_role.id, sample_permission.id
        )


def test_remove_permission_from_role(
    role_permissions_repo, sample_role, sample_permission
):
    role_permissions_repo.assign_permission_to_role(
        sample_role.id, sample_permission.id
    )
    assert role_permissions_repo.exists(sample_role.id, sample_permission.id) is True

    role_permissions_repo.remove_permission_from_role(
        sample_role.id, sample_permission.id
    )
    assert role_permissions_repo.exists(sample_role.id, sample_permission.id) is False


def test_remove_permission_not_found(
    role_permissions_repo, sample_role, sample_permission
):
    with pytest.raises(RolePermissionNotFoundError):
        role_permissions_repo.remove_permission_from_role(
            sample_role.id, sample_permission.id
        )


def test_list_permissions_for_role(role_permissions_repo, sample_role, db_session):
    p1 = Permission(
        permission_code="PERM1",
        permission_name="Perm 1",
        action=PermissionAction.READ,
        status=PermissionStatus.ACTIVE,
    )
    p2 = Permission(
        permission_code="PERM2",
        permission_name="Perm 2",
        action=PermissionAction.CREATE,
        status=PermissionStatus.ACTIVE,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    role_permissions_repo.assign_permission_to_role(sample_role.id, p1.id)
    role_permissions_repo.assign_permission_to_role(sample_role.id, p2.id)

    perms = role_permissions_repo.list_permissions_for_role(sample_role.id)
    assert len(perms) == 2
    assert {p.permission_code for p in perms} == {"PERM1", "PERM2"}


def test_list_roles_for_permission(
    role_permissions_repo, sample_permission, db_session
):
    r1 = Role(
        role_code="ROLE1",
        role_name="Role 1",
        role_type=RoleType.SYSTEM,
        status=RoleStatus.ACTIVE,
    )
    r2 = Role(
        role_code="ROLE2",
        role_name="Role 2",
        role_type=RoleType.CUSTOM,
        status=RoleStatus.ACTIVE,
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    role_permissions_repo.assign_permission_to_role(r1.id, sample_permission.id)
    role_permissions_repo.assign_permission_to_role(r2.id, sample_permission.id)

    roles = role_permissions_repo.list_roles_for_permission(sample_permission.id)
    assert len(roles) == 2
    assert {r.role_code for r in roles} == {"ROLE1", "ROLE2"}


def test_sqlalchemy_errors(role_permissions_repo, sample_role, sample_permission):
    with patch.object(
        role_permissions_repo._session,
        "execute",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.assign_permission_to_role(
                sample_role.id, sample_permission.id
            )

    with patch.object(
        role_permissions_repo._session,
        "execute",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.remove_permission_from_role(
                sample_role.id, sample_permission.id
            )

    with patch.object(
        role_permissions_repo._session,
        "execute",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.list_permissions_for_role(sample_role.id)

    with patch.object(
        role_permissions_repo._session,
        "execute",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.list_roles_for_permission(sample_permission.id)

    with patch.object(
        role_permissions_repo._session,
        "execute",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.exists(sample_role.id, sample_permission.id)


def test_assign_permission_error_after_exists(
    role_permissions_repo, sample_role, sample_permission
):
    with patch.object(
        role_permissions_repo._session,
        "add",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.assign_permission_to_role(
                sample_role.id, sample_permission.id
            )


def test_remove_permission_error_after_fetch(
    role_permissions_repo, sample_role, sample_permission
):
    role_permissions_repo.assign_permission_to_role(
        sample_role.id, sample_permission.id
    )
    with patch.object(
        role_permissions_repo._session,
        "delete",
        side_effect=SQLAlchemyError("mocked error"),
    ):
        with pytest.raises(RolePermissionsRepositoryError):
            role_permissions_repo.remove_permission_from_role(
                sample_role.id, sample_permission.id
            )


def test_role_permission_repr(sample_role, sample_permission):
    from app.role_permissions.models import RolePermission

    rp = RolePermission(role_id=sample_role.id, permission_id=sample_permission.id)
    assert repr(rp) == f"<RolePermission(role_id={
            sample_role.id!r}, permission_id={
            sample_permission.id!r})>"

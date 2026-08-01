import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.role_permissions.service import RolePermissionService
from app.role_permissions.exceptions import (
    RolePermissionsRepositoryError,
    RolePermissionNotFoundError,
    RolePermissionAlreadyExistsError,
    RolePermissionsServiceError,
    ValidationError,
)


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def mock_roles_repo():
    return MagicMock()


@pytest.fixture
def mock_permissions_repo():
    return MagicMock()


@pytest.fixture
def service(mock_repo, mock_roles_repo, mock_permissions_repo):
    return RolePermissionService(
        repository=mock_repo,
        roles_repository=mock_roles_repo,
        permissions_repository=mock_permissions_repo,
    )


def test_assign_permission_success(
    service, mock_repo, mock_roles_repo, mock_permissions_repo
):
    role_id = uuid4()
    permission_id = uuid4()
    user_id = uuid4()

    mock_roles_repo.get_by_id.return_value = "role"
    mock_permissions_repo.get_by_id.return_value = "perm"
    mock_repo.assign_permission_to_role.return_value = "rp"

    res = service.assign_permission(role_id, permission_id, user_id)
    assert res == "rp"
    mock_repo.assign_permission_to_role.assert_called_with(
        role_id, permission_id, user_id
    )


def test_assign_permission_role_not_found(service, mock_roles_repo):
    role_id = uuid4()
    mock_roles_repo.get_by_id.return_value = None
    with pytest.raises(ValidationError) as exc:
        service.assign_permission(role_id, uuid4())
    assert "Role does not exist" in str(exc.value)


def test_assign_permission_role_error(service, mock_roles_repo):
    role_id = uuid4()
    mock_roles_repo.get_by_id.side_effect = Exception("fail")
    with pytest.raises(RolePermissionsServiceError):
        service.assign_permission(role_id, uuid4())


def test_assign_permission_permission_not_found(
    service, mock_roles_repo, mock_permissions_repo
):
    role_id = uuid4()
    permission_id = uuid4()
    mock_roles_repo.get_by_id.return_value = "role"
    mock_permissions_repo.get_by_id.return_value = None
    with pytest.raises(ValidationError) as exc:
        service.assign_permission(role_id, permission_id)
    assert "Permission does not exist" in str(exc.value)


def test_assign_permission_permission_error(
    service, mock_roles_repo, mock_permissions_repo
):
    role_id = uuid4()
    permission_id = uuid4()
    mock_roles_repo.get_by_id.return_value = "role"
    mock_permissions_repo.get_by_id.side_effect = Exception("fail")
    with pytest.raises(RolePermissionsServiceError):
        service.assign_permission(role_id, permission_id)


def test_assign_permission_already_exists(
    service, mock_repo, mock_roles_repo, mock_permissions_repo
):
    role_id = uuid4()
    permission_id = uuid4()
    mock_roles_repo.get_by_id.return_value = "role"
    mock_permissions_repo.get_by_id.return_value = "perm"
    mock_repo.assign_permission_to_role.side_effect = RolePermissionAlreadyExistsError(
        "exists"
    )
    with pytest.raises(ValidationError):
        service.assign_permission(role_id, permission_id)


def test_assign_permission_repo_error(
    service, mock_repo, mock_roles_repo, mock_permissions_repo
):
    role_id = uuid4()
    permission_id = uuid4()
    mock_roles_repo.get_by_id.return_value = "role"
    mock_permissions_repo.get_by_id.return_value = "perm"
    mock_repo.assign_permission_to_role.side_effect = RolePermissionsRepositoryError(
        "fail"
    )
    with pytest.raises(RolePermissionsServiceError):
        service.assign_permission(role_id, permission_id)


def test_remove_permission_success(service, mock_repo):
    role_id = uuid4()
    permission_id = uuid4()
    mock_repo.remove_permission_from_role.return_value = True
    assert service.remove_permission(role_id, permission_id) is True


def test_remove_permission_not_found(service, mock_repo):
    role_id = uuid4()
    permission_id = uuid4()
    mock_repo.remove_permission_from_role.side_effect = RolePermissionNotFoundError(
        "nf"
    )
    with pytest.raises(ValidationError):
        service.remove_permission(role_id, permission_id)


def test_remove_permission_repo_error(service, mock_repo):
    role_id = uuid4()
    permission_id = uuid4()
    mock_repo.remove_permission_from_role.side_effect = RolePermissionsRepositoryError(
        "fail"
    )
    with pytest.raises(RolePermissionsServiceError):
        service.remove_permission(role_id, permission_id)


def test_list_permissions_for_role(service, mock_repo):
    role_id = uuid4()
    mock_repo.list_permissions_for_role.return_value = ["p1", "p2"]
    assert service.list_permissions_for_role(role_id) == ["p1", "p2"]


def test_list_permissions_for_role_error(service, mock_repo):
    role_id = uuid4()
    mock_repo.list_permissions_for_role.side_effect = RolePermissionsRepositoryError(
        "fail"
    )
    with pytest.raises(RolePermissionsServiceError):
        service.list_permissions_for_role(role_id)


def test_list_roles_for_permission(service, mock_repo):
    permission_id = uuid4()
    mock_repo.list_roles_for_permission.return_value = ["r1", "r2"]
    assert service.list_roles_for_permission(permission_id) == ["r1", "r2"]


def test_list_roles_for_permission_error(service, mock_repo):
    permission_id = uuid4()
    mock_repo.list_roles_for_permission.side_effect = RolePermissionsRepositoryError(
        "fail"
    )
    with pytest.raises(RolePermissionsServiceError):
        service.list_roles_for_permission(permission_id)


def test_exists(service, mock_repo):
    role_id = uuid4()
    permission_id = uuid4()
    mock_repo.exists.return_value = True
    assert service.exists(role_id, permission_id) is True


def test_exists_error(service, mock_repo):
    role_id = uuid4()
    permission_id = uuid4()
    mock_repo.exists.side_effect = RolePermissionsRepositoryError("fail")
    with pytest.raises(RolePermissionsServiceError):
        service.exists(role_id, permission_id)


def test_count_permissions_for_role(service, mock_repo):
    role_id = uuid4()
    mock_repo.list_permissions_for_role.return_value = ["p1", "p2"]
    assert service.count_permissions_for_role(role_id) == 2


def test_count_roles_for_permission(service, mock_repo):
    permission_id = uuid4()
    mock_repo.list_roles_for_permission.return_value = ["r1", "r2", "r3"]
    assert service.count_roles_for_permission(permission_id) == 3

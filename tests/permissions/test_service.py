import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.permissions.service import PermissionsService
from app.permissions.exceptions import (
    PermissionsRepositoryError,
    PermissionNotFoundError,
    PermissionsServiceError,
    DuplicatePermissionError,
    ValidationError,
)
from app.permissions.models import Permission


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def service(mock_repo):
    return PermissionsService(repository=mock_repo)


def test_create_permission_success(service, mock_repo):
    data = {
        "permission_code": "PERM_READ",
        "permission_name": "Permission Read",
        "description": "Permission description",
    }
    mock_repo.exists_by_permission_code.return_value = False
    mock_repo.exists_by_permission_name.return_value = False

    mock_permission = MagicMock()
    mock_repo.create.return_value = mock_permission

    result = service.create_permission(data)
    assert result == mock_permission
    mock_repo.create.assert_called_once()


def test_create_permission_missing_fields(service):
    with pytest.raises(ValidationError):
        service.create_permission({"permission_code": "A"})


def test_create_permission_duplicate_code(service, mock_repo):
    data = {"permission_code": "A", "permission_name": "Permission"}
    mock_repo.exists_by_permission_code.return_value = True
    with pytest.raises(DuplicatePermissionError) as exc:
        service.create_permission(data)
    assert "Permission code" in str(exc.value)


def test_create_permission_duplicate_name(service, mock_repo):
    data = {"permission_code": "A", "permission_name": "Permission"}
    mock_repo.exists_by_permission_code.return_value = False
    mock_repo.exists_by_permission_name.return_value = True
    with pytest.raises(DuplicatePermissionError) as exc:
        service.create_permission(data)
    assert "Permission name" in str(exc.value)


def test_create_permission_repo_error_exists(service, mock_repo):
    data = {"permission_code": "A", "permission_name": "Permission"}
    mock_repo.exists_by_permission_code.side_effect = PermissionsRepositoryError(
        "DB fail"
    )
    with pytest.raises(PermissionsServiceError):
        service.create_permission(data)


def test_create_permission_repo_error_create(service, mock_repo):
    data = {"permission_code": "A", "permission_name": "Permission"}
    mock_repo.exists_by_permission_code.return_value = False
    mock_repo.exists_by_permission_name.return_value = False

    mock_repo.create.side_effect = PermissionsRepositoryError("DB fail")
    with pytest.raises(PermissionsServiceError):
        service.create_permission(data)


def test_get_permission_success(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "mock_permission"
    assert service.get_permission(uid) == "mock_permission"


def test_get_permission_not_found(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(PermissionNotFoundError):
        service.get_permission(uid)


def test_get_permission_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.get_permission(uid)


def test_list_permissions_success(service, mock_repo):
    mock_repo.list.return_value = ["p1", "p2"]
    assert service.list_permissions(0, 10) == ["p1", "p2"]


def test_list_permissions_repo_error(service, mock_repo):
    mock_repo.list.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.list_permissions()


def test_update_permission(service, mock_repo):
    uid = uuid4()
    permission = Permission(
        permission_code="P", permission_name="old_n", description="old_d"
    )
    permission.id = uid
    mock_repo.get_by_id.return_value = permission

    mock_repo.exists_by_permission_name.return_value = False
    mock_repo.update.return_value = permission

    res = service.update_permission(
        uid,
        {
            "permission_name": "new_n",
            "description": "new_d",
            "action": "execute",
            "status": "inactive",
        },
    )

    assert res.permission_name == "new_n"
    assert res.description == "new_d"
    assert res.status == "inactive"
    assert res.action == "execute"


def test_update_permission_duplicate_name(service, mock_repo):
    uid = uuid4()
    permission = Permission(permission_name="old_n")
    permission.id = uid
    mock_repo.get_by_id.return_value = permission
    mock_repo.exists_by_permission_name.return_value = True

    with pytest.raises(DuplicatePermissionError):
        service.update_permission(uid, {"permission_name": "new_n"})


def test_update_permission_validation_repo_error(service, mock_repo):
    uid = uuid4()
    permission = Permission(permission_name="old_n")
    permission.id = uid
    mock_repo.get_by_id.return_value = permission
    mock_repo.exists_by_permission_name.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.update_permission(uid, {"permission_name": "new_n"})


def test_update_permission_repo_error(service, mock_repo):
    uid = uuid4()
    permission = Permission(permission_name="old_n")
    permission.id = uid
    mock_repo.get_by_id.return_value = permission
    mock_repo.update.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.update_permission(uid, {"description": "New Desc"})


def test_patch_permission(service, mock_repo):
    uid = uuid4()
    permission = Permission()
    permission.id = uid
    mock_repo.get_by_id.return_value = permission
    mock_repo.update.return_value = permission
    assert service.patch_permission(uid, {}) == permission


def test_delete_permission(service, mock_repo):
    uid = uuid4()
    mock_permission = MagicMock()
    mock_repo.get_by_id.return_value = mock_permission
    mock_repo.delete.return_value = True
    assert service.delete_permission(uid) is True


def test_delete_permission_repo_error(service, mock_repo):
    uid = uuid4()
    mock_permission = MagicMock()
    mock_repo.get_by_id.return_value = mock_permission
    mock_repo.delete.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.delete_permission(uid)


def test_search_permissions(service, mock_repo):
    mock_repo.search.return_value = ["p1"]
    res = service.search_permissions("app")
    assert len(res) == 1
    mock_repo.search.assert_called_with(permission_name="app", limit=100)


def test_search_permissions_repo_error(service, mock_repo):
    mock_repo.search.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.search_permissions("test")


def test_count_permissions(service, mock_repo):
    mock_repo.count.return_value = 5
    assert service.count_permissions() == 5


def test_count_permissions_repo_error(service, mock_repo):
    mock_repo.count.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.count_permissions()


def test_activate_permission(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "p1"
    mock_repo.activate.return_value = "active_p1"
    assert service.activate_permission(uid) == "active_p1"


def test_activate_permission_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "p1"
    mock_repo.activate.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.activate_permission(uid)


def test_deactivate_permission(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "p1"
    mock_repo.deactivate.return_value = "deactive_p1"
    assert service.deactivate_permission(uid) == "deactive_p1"


def test_deactivate_permission_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "p1"
    mock_repo.deactivate.side_effect = PermissionsRepositoryError("fail")
    with pytest.raises(PermissionsServiceError):
        service.deactivate_permission(uid)

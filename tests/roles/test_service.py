import pytest
from unittest.mock import MagicMock, call
from uuid import uuid4

from app.roles.service import RolesService
from app.roles.exceptions import (
    RolesRepositoryError,
    RoleNotFoundError,
    RolesServiceError,
    DuplicateRoleError,
    ValidationError
)
from app.roles.models import Role, RoleType

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def service(mock_repo):
    return RolesService(repository=mock_repo)

def test_create_role_success(service, mock_repo):
    data = {
        "role_code": "ADMIN",
        "role_name": "Administrator",
        "description": "Admin role"
    }
    mock_repo.exists_by_role_code.return_value = False
    mock_repo.exists_by_role_name.return_value = False
    
    mock_role = MagicMock()
    mock_repo.create.return_value = mock_role
    
    result = service.create_role(data)
    assert result == mock_role
    mock_repo.create.assert_called_once()

def test_create_role_missing_fields(service):
    with pytest.raises(ValidationError):
        service.create_role({"role_code": "A"})

def test_create_role_duplicate_role_code(service, mock_repo):
    data = {"role_code": "A", "role_name": "Admin"}
    mock_repo.exists_by_role_code.return_value = True
    with pytest.raises(DuplicateRoleError) as exc:
        service.create_role(data)
    assert "Role code" in str(exc.value)

def test_create_role_duplicate_role_name(service, mock_repo):
    data = {"role_code": "A", "role_name": "Admin"}
    mock_repo.exists_by_role_code.return_value = False
    mock_repo.exists_by_role_name.return_value = True
    with pytest.raises(DuplicateRoleError) as exc:
        service.create_role(data)
    assert "Role name" in str(exc.value)

def test_create_role_repo_error_exists(service, mock_repo):
    data = {"role_code": "A", "role_name": "Admin"}
    mock_repo.exists_by_role_code.side_effect = RolesRepositoryError("DB fail")
    with pytest.raises(RolesServiceError):
        service.create_role(data)

def test_create_role_repo_error_create(service, mock_repo):
    data = {"role_code": "A", "role_name": "Admin"}
    mock_repo.exists_by_role_code.return_value = False
    mock_repo.exists_by_role_name.return_value = False
    
    mock_repo.create.side_effect = RolesRepositoryError("DB fail")
    with pytest.raises(RolesServiceError):
        service.create_role(data)

def test_get_role_success(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "mock_role"
    assert service.get_role(uid) == "mock_role"

def test_get_role_not_found(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(RoleNotFoundError):
        service.get_role(uid)

def test_get_role_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.get_role(uid)

def test_list_roles_success(service, mock_repo):
    mock_repo.list.return_value = ["r1", "r2"]
    assert service.list_roles(0, 10) == ["r1", "r2"]

def test_list_roles_repo_error(service, mock_repo):
    mock_repo.list.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.list_roles()

def test_update_role(service, mock_repo):
    uid = uuid4()
    role = Role(role_code="R", role_name="old_n", description="old_d")
    role.id = uid
    mock_repo.get_by_id.return_value = role
    
    mock_repo.exists_by_role_name.return_value = False
    mock_repo.update.return_value = role
    
    res = service.update_role(uid, {
        "role_name": "new_n",
        "description": "new_d",
        "status": "inactive"
    })
    
    assert res.role_name == "new_n"
    assert res.description == "new_d"
    assert res.status == "inactive"

def test_update_role_duplicate_name(service, mock_repo):
    uid = uuid4()
    role = Role(role_name="old_n")
    role.id = uid
    mock_repo.get_by_id.return_value = role
    mock_repo.exists_by_role_name.return_value = True
    
    with pytest.raises(DuplicateRoleError):
        service.update_role(uid, {"role_name": "new_n"})

def test_update_role_validation_repo_error(service, mock_repo):
    uid = uuid4()
    role = Role(role_name="old_n")
    role.id = uid
    mock_repo.get_by_id.return_value = role
    mock_repo.exists_by_role_name.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.update_role(uid, {"role_name": "new_n"})

def test_update_role_repo_error(service, mock_repo):
    uid = uuid4()
    role = Role(role_name="old_n")
    role.id = uid
    mock_repo.get_by_id.return_value = role
    mock_repo.update.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.update_role(uid, {"description": "New Desc"})

def test_patch_role(service, mock_repo):
    uid = uuid4()
    role = Role()
    role.id = uid
    mock_repo.get_by_id.return_value = role
    mock_repo.update.return_value = role
    assert service.patch_role(uid, {}) == role

def test_delete_role(service, mock_repo):
    uid = uuid4()
    mock_role = MagicMock()
    mock_role.role_type = RoleType.CUSTOM
    mock_repo.get_by_id.return_value = mock_role
    mock_repo.delete.return_value = True
    assert service.delete_role(uid) is True

def test_delete_role_system(service, mock_repo):
    uid = uuid4()
    mock_role = MagicMock()
    mock_role.role_type = RoleType.SYSTEM
    mock_repo.get_by_id.return_value = mock_role
    with pytest.raises(ValidationError) as exc:
        service.delete_role(uid)
    assert "Cannot delete system roles" in str(exc.value)

def test_delete_role_repo_error(service, mock_repo):
    uid = uuid4()
    mock_role = MagicMock()
    mock_role.role_type = RoleType.CUSTOM
    mock_repo.get_by_id.return_value = mock_role
    mock_repo.delete.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.delete_role(uid)

def test_search_roles(service, mock_repo):
    mock_repo.search.return_value = ["r1"]
    res = service.search_roles("admin")
    assert len(res) == 1
    mock_repo.search.assert_called_with(role_name="admin", limit=100)

def test_search_roles_repo_error(service, mock_repo):
    mock_repo.search.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.search_roles("test")

def test_count_roles(service, mock_repo):
    mock_repo.count.return_value = 5
    assert service.count_roles() == 5

def test_count_roles_repo_error(service, mock_repo):
    mock_repo.count.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.count_roles()

def test_activate_role(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.activate.return_value = "active_r1"
    assert service.activate_role(uid) == "active_r1"

def test_activate_role_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.activate.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.activate_role(uid)

def test_deactivate_role(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.deactivate.return_value = "deactive_r1"
    assert service.deactivate_role(uid) == "deactive_r1"

def test_deactivate_role_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.deactivate.side_effect = RolesRepositoryError("fail")
    with pytest.raises(RolesServiceError):
        service.deactivate_role(uid)

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.user_roles.service import UserRoleService
from app.user_roles.exceptions import (
    UserRolesRepositoryError,
    UserRoleNotFoundError,
    UserRoleAlreadyExistsError,
    UserRolesServiceError,
    ValidationError
)

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def mock_roles_repo():
    return MagicMock()

@pytest.fixture
def mock_users_repo():
    return MagicMock()

@pytest.fixture
def service(mock_repo, mock_roles_repo, mock_users_repo):
    return UserRoleService(
        repository=mock_repo,
        roles_repository=mock_roles_repo,
        users_repository=mock_users_repo
    )

def test_assign_role_success(service, mock_repo, mock_roles_repo, mock_users_repo):
    user_id = uuid4()
    role_id = uuid4()
    assigner_id = uuid4()
    
    mock_users_repo.get_by_id.return_value = "user"
    mock_roles_repo.get_by_id.return_value = MagicMock(role_name="Admin")
    mock_repo.assign_role_to_user.return_value = "ur"
    
    res = service.assign_role(user_id, role_id, assigner_id)
    assert res == "ur"
    mock_repo.assign_role_to_user.assert_called_with(user_id, role_id, assigner_id)

def test_assign_role_user_not_found(service, mock_users_repo):
    user_id = uuid4()
    mock_users_repo.get_by_id.return_value = None
    with pytest.raises(ValidationError) as exc:
        service.assign_role(user_id, uuid4())
    assert "User does not exist" in str(exc.value)

def test_assign_role_user_error(service, mock_users_repo):
    user_id = uuid4()
    mock_users_repo.get_by_id.side_effect = Exception("fail")
    with pytest.raises(UserRolesServiceError):
        service.assign_role(user_id, uuid4())

def test_assign_role_role_not_found(service, mock_users_repo, mock_roles_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_users_repo.get_by_id.return_value = "user"
    mock_roles_repo.get_by_id.return_value = None
    with pytest.raises(ValidationError) as exc:
        service.assign_role(user_id, role_id)
    assert "Role does not exist" in str(exc.value)

def test_assign_role_role_error(service, mock_users_repo, mock_roles_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_users_repo.get_by_id.return_value = "user"
    mock_roles_repo.get_by_id.side_effect = Exception("fail")
    with pytest.raises(UserRolesServiceError):
        service.assign_role(user_id, role_id)

def test_assign_role_already_exists(service, mock_repo, mock_users_repo, mock_roles_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_users_repo.get_by_id.return_value = "user"
    mock_roles_repo.get_by_id.return_value = "role"
    mock_repo.assign_role_to_user.side_effect = UserRoleAlreadyExistsError("exists")
    with pytest.raises(ValidationError):
        service.assign_role(user_id, role_id)

def test_assign_role_repo_error(service, mock_repo, mock_users_repo, mock_roles_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_users_repo.get_by_id.return_value = "user"
    mock_roles_repo.get_by_id.return_value = "role"
    mock_repo.assign_role_to_user.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.assign_role(user_id, role_id)

def test_remove_role_success(service, mock_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_repo.remove_role_from_user.return_value = True
    assert service.remove_role(user_id, role_id) is True

def test_remove_role_not_found(service, mock_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_repo.remove_role_from_user.side_effect = UserRoleNotFoundError("nf")
    with pytest.raises(ValidationError):
        service.remove_role(user_id, role_id)

def test_remove_role_repo_error(service, mock_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_repo.remove_role_from_user.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.remove_role(user_id, role_id)

def test_list_roles_for_user(service, mock_repo):
    user_id = uuid4()
    mock_repo.list_roles_for_user.return_value = ["r1", "r2"]
    assert service.list_roles_for_user(user_id) == ["r1", "r2"]

def test_list_roles_for_user_error(service, mock_repo):
    user_id = uuid4()
    mock_repo.list_roles_for_user.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.list_roles_for_user(user_id)

def test_list_users_for_role(service, mock_repo):
    role_id = uuid4()
    mock_repo.list_users_for_role.return_value = ["u1", "u2"]
    assert service.list_users_for_role(role_id) == ["u1", "u2"]

def test_list_users_for_role_error(service, mock_repo):
    role_id = uuid4()
    mock_repo.list_users_for_role.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.list_users_for_role(role_id)

def test_exists(service, mock_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_repo.exists.return_value = True
    assert service.exists(user_id, role_id) is True

def test_exists_error(service, mock_repo):
    user_id = uuid4()
    role_id = uuid4()
    mock_repo.exists.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.exists(user_id, role_id)

def test_count_roles_for_user(service, mock_repo):
    user_id = uuid4()
    mock_repo.count_roles_for_user.return_value = 2
    assert service.count_roles_for_user(user_id) == 2

def test_count_roles_for_user_error(service, mock_repo):
    user_id = uuid4()
    mock_repo.count_roles_for_user.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.count_roles_for_user(user_id)

def test_count_users_for_role(service, mock_repo):
    role_id = uuid4()
    mock_repo.count_users_for_role.return_value = 3
    assert service.count_users_for_role(role_id) == 3

def test_count_users_for_role_error(service, mock_repo):
    role_id = uuid4()
    mock_repo.count_users_for_role.side_effect = UserRolesRepositoryError("fail")
    with pytest.raises(UserRolesServiceError):
        service.count_users_for_role(role_id)

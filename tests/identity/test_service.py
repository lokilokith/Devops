from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from app.identity.exceptions import (
    DuplicateUserError,
    IdentityRepositoryError,
    IdentityServiceError,
    UserNotFoundError,
    ValidationError,
)
from app.identity.models import User
from app.identity.service import IdentityService


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.hash_password.return_value = "hashed_pass"
    return auth


@pytest.fixture
def service(mock_repo, mock_auth):
    return IdentityService(repository=mock_repo, auth_service=mock_auth)


def test_create_user_success(service, mock_repo):
    data = {
        "username": "testuser",
        "email": "test@test.com",
        "employee_id": "E1",
        "password": "pass",
    }
    mock_repo.exists_by_username.return_value = False
    mock_repo.exists_by_email.return_value = False
    mock_repo.list_users.return_value = []

    mock_user = MagicMock()
    mock_repo.create_user.return_value = mock_user

    result = service.create_user(data)
    assert result == mock_user
    mock_repo.create_user.assert_called_once()

    # Assert hash is called
    service._auth_service.hash_password.assert_called_with("pass")


def test_create_user_missing_fields(service):
    with pytest.raises(ValidationError):
        service.create_user({"username": "u"})


def test_create_user_duplicate_username(service, mock_repo):
    data = {"username": "u", "email": "e", "employee_id": "E1", "password": "p"}
    mock_repo.exists_by_username.return_value = True
    with pytest.raises(DuplicateUserError) as exc:
        service.create_user(data)
    assert "Username" in str(exc.value)


def test_create_user_duplicate_email(service, mock_repo):
    data = {"username": "u", "email": "e", "employee_id": "E1", "password": "p"}
    mock_repo.exists_by_username.return_value = False
    mock_repo.exists_by_email.return_value = True
    with pytest.raises(DuplicateUserError) as exc:
        service.create_user(data)
    assert "Email" in str(exc.value)


def test_create_user_duplicate_employee_id(service, mock_repo):
    data = {"username": "u", "email": "e", "employee_id": "E1", "password": "p"}
    mock_repo.exists_by_username.return_value = False
    mock_repo.exists_by_email.return_value = False

    existing_user = User(employee_id="E1")
    existing_user.id = uuid4()
    mock_repo.list_users.side_effect = [[existing_user], []]

    with pytest.raises(DuplicateUserError) as exc:
        service.create_user(data)
    assert "Employee ID" in str(exc.value)


def test_create_user_repo_error_exists(service, mock_repo):
    data = {"username": "u", "email": "e", "employee_id": "E1", "password": "p"}
    mock_repo.exists_by_username.side_effect = IdentityRepositoryError("DB fail")
    with pytest.raises(IdentityServiceError):
        service.create_user(data)


def test_create_user_repo_error_create(service, mock_repo):
    data = {"username": "u", "email": "e", "employee_id": "E1", "password": "p"}
    mock_repo.exists_by_username.return_value = False
    mock_repo.exists_by_email.return_value = False
    mock_repo.list_users.return_value = []

    mock_repo.create_user.side_effect = IdentityRepositoryError("DB fail")
    with pytest.raises(IdentityServiceError):
        service.create_user(data)


def test_get_user_success(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "mock_user"
    assert service.get_user(uid) == "mock_user"


def test_get_user_not_found(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(UserNotFoundError):
        service.get_user(uid)


def test_get_user_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.get_user(uid)


def test_list_users_success(service, mock_repo):
    mock_repo.list_users.return_value = ["u1", "u2"]
    assert service.list_users(0, 10) == ["u1", "u2"]


def test_list_users_repo_error(service, mock_repo):
    mock_repo.list_users.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.list_users()


def test_update_user(service, mock_repo):
    uid = uuid4()
    user = User(username="old_u", email="old_e", employee_id="old_e1", status="active")
    user.id = uid
    mock_repo.get_by_id.return_value = user

    mock_repo.exists_by_username.return_value = False
    mock_repo.exists_by_email.return_value = False
    mock_repo.list_users.return_value = []
    mock_repo.update_user.return_value = user

    res = service.update_user(
        uid,
        {
            "username": "new_u",
            "email": "new_e",
            "employee_id": "new_e1",
            "full_name": "New",
            "title": "T",
            "status": "disabled",
            "password": "new_password",
        },
    )

    assert res.username == "new_u"
    assert res.full_name == "New"
    assert res.password_hash == "hashed_pass"


def test_update_user_duplicate_username(service, mock_repo):
    uid = uuid4()
    user = User(username="old_u")
    user.id = uid
    mock_repo.get_by_id.return_value = user
    mock_repo.exists_by_username.return_value = True

    with pytest.raises(DuplicateUserError):
        service.update_user(uid, {"username": "new_u"})


def test_update_user_duplicate_email(service, mock_repo):
    uid = uuid4()
    user = User(username="old_u", email="old_e")
    user.id = uid
    mock_repo.get_by_id.return_value = user
    mock_repo.exists_by_email.return_value = True

    with pytest.raises(DuplicateUserError):
        service.update_user(uid, {"email": "new_e"})


def test_update_user_validation_repo_errors(service, mock_repo):
    uid = uuid4()
    user = User(username="old_u")
    user.id = uid
    mock_repo.get_by_id.return_value = user
    mock_repo.exists_by_username.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.update_user(uid, {"username": "new_u"})

    user.username = "new_u"
    user.email = "old_e"
    mock_repo.exists_by_username.side_effect = None
    mock_repo.exists_by_email.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.update_user(uid, {"email": "new_e"})


def test_update_user_repo_error(service, mock_repo):
    uid = uuid4()
    user = User(username="old_u")
    user.id = uid
    mock_repo.get_by_id.return_value = user
    mock_repo.update_user.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.update_user(uid, {"full_name": "New Name"})


def test_patch_user(service, mock_repo):
    uid = uuid4()
    user = User()
    user.id = uid
    mock_repo.get_by_id.return_value = user
    mock_repo.update_user.return_value = user
    assert service.patch_user(uid, {}) == user


def test_delete_user(service, mock_repo):
    uid = uuid4()
    mock_repo.delete_user.return_value = True
    assert service.delete_user(uid) is True


def test_delete_user_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.delete_user.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.delete_user(uid)


def test_search_users(service, mock_repo):
    u1 = User(
        username="admin", email="admin@test.com", employee_id="1", full_name="Admin"
    )
    u2 = User(
        username="guest", email="guest@test.com", employee_id="2", full_name="Guest"
    )
    mock_repo.list_users.side_effect = [[u1, u2], []]

    res = service.search_users("admin")
    assert len(res) == 1
    assert res[0] == u1

    # search is case insensitive
    mock_repo.list_users.side_effect = [[u1, u2], []]
    res = service.search_users("GUEST")
    assert len(res) == 1
    assert res[0] == u2

    res = service.search_users("")
    assert len(res) == 0


def test_search_users_repo_error(service, mock_repo):
    mock_repo.list_users.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.search_users("test")


def test_count_users(service, mock_repo):
    mock_repo.list_users.side_effect = [[1, 2, 3], [4, 5], []]
    assert service.count_users() == 5


def test_count_users_repo_error(service, mock_repo):
    mock_repo.list_users.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service.count_users()


def test_validate_duplicate_employee_id_repo_error(service, mock_repo):
    mock_repo.list_users.side_effect = IdentityRepositoryError("fail")
    with pytest.raises(IdentityServiceError):
        service._validate_duplicate_employee_id("E1")


def test_validate_duplicate_employee_id_exclude_user(service, mock_repo):
    uid = uuid4()
    u = User(employee_id="E1")
    u.id = uid
    mock_repo.list_users.side_effect = [[u], []]

    # Should not raise exception
    service._validate_duplicate_employee_id("E1", exclude_user_id=uid)

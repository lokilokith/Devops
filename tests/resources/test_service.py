from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.resources.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ResourcesRepositoryError,
    ResourcesServiceError,
    ValidationError,
)
from app.resources.models import Resource
from app.resources.service import ResourcesService


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def service(mock_repo):
    return ResourcesService(repository=mock_repo)


def test_create_resource_success(service, mock_repo):
    data = {
        "resource_code": "SRV",
        "resource_name": "Server",
        "description": "Server description",
    }
    mock_repo.exists_by_resource_code.return_value = False
    mock_repo.exists_by_resource_name.return_value = False

    mock_resource = MagicMock()
    mock_repo.create.return_value = mock_resource

    result = service.create_resource(data)
    assert result == mock_resource
    mock_repo.create.assert_called_once()


def test_create_resource_missing_fields(service):
    with pytest.raises(ValidationError):
        service.create_resource({"resource_code": "A"})


def test_create_resource_duplicate_code(service, mock_repo):
    data = {"resource_code": "A", "resource_name": "Resource"}
    mock_repo.exists_by_resource_code.return_value = True
    with pytest.raises(DuplicateResourceError) as exc:
        service.create_resource(data)
    assert "Resource code" in str(exc.value)


def test_create_resource_duplicate_name(service, mock_repo):
    data = {"resource_code": "A", "resource_name": "Resource"}
    mock_repo.exists_by_resource_code.return_value = False
    mock_repo.exists_by_resource_name.return_value = True
    with pytest.raises(DuplicateResourceError) as exc:
        service.create_resource(data)
    assert "Resource name" in str(exc.value)


def test_create_resource_repo_error_exists(service, mock_repo):
    data = {"resource_code": "A", "resource_name": "Resource"}
    mock_repo.exists_by_resource_code.side_effect = ResourcesRepositoryError("DB fail")
    with pytest.raises(ResourcesServiceError):
        service.create_resource(data)


def test_create_resource_repo_error_create(service, mock_repo):
    data = {"resource_code": "A", "resource_name": "Resource"}
    mock_repo.exists_by_resource_code.return_value = False
    mock_repo.exists_by_resource_name.return_value = False

    mock_repo.create.side_effect = ResourcesRepositoryError("DB fail")
    with pytest.raises(ResourcesServiceError):
        service.create_resource(data)


def test_get_resource_success(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "mock_resource"
    assert service.get_resource(uid) == "mock_resource"


def test_get_resource_not_found(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(ResourceNotFoundError):
        service.get_resource(uid)


def test_get_resource_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.get_resource(uid)


def test_list_resources_success(service, mock_repo):
    mock_repo.list.return_value = ["r1", "r2"]
    assert service.list_resources(0, 10) == ["r1", "r2"]


def test_list_resources_repo_error(service, mock_repo):
    mock_repo.list.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.list_resources()


def test_update_resource(service, mock_repo):
    uid = uuid4()
    resource = Resource(resource_code="R", resource_name="old_n", description="old_d")
    resource.id = uid
    mock_repo.get_by_id.return_value = resource

    mock_repo.exists_by_resource_name.return_value = False
    mock_repo.update.return_value = resource

    res = service.update_resource(
        uid,
        {
            "resource_name": "new_n",
            "description": "new_d",
            "resource_type": "database",
            "status": "inactive",
        },
    )

    assert res.resource_name == "new_n"
    assert res.description == "new_d"
    assert res.status == "inactive"
    assert res.resource_type == "database"


def test_update_resource_duplicate_name(service, mock_repo):
    uid = uuid4()
    resource = Resource(resource_name="old_n")
    resource.id = uid
    mock_repo.get_by_id.return_value = resource
    mock_repo.exists_by_resource_name.return_value = True

    with pytest.raises(DuplicateResourceError):
        service.update_resource(uid, {"resource_name": "new_n"})


def test_update_resource_validation_repo_error(service, mock_repo):
    uid = uuid4()
    resource = Resource(resource_name="old_n")
    resource.id = uid
    mock_repo.get_by_id.return_value = resource
    mock_repo.exists_by_resource_name.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.update_resource(uid, {"resource_name": "new_n"})


def test_update_resource_repo_error(service, mock_repo):
    uid = uuid4()
    resource = Resource(resource_name="old_n")
    resource.id = uid
    mock_repo.get_by_id.return_value = resource
    mock_repo.update.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.update_resource(uid, {"description": "New Desc"})


def test_patch_resource(service, mock_repo):
    uid = uuid4()
    resource = Resource()
    resource.id = uid
    mock_repo.get_by_id.return_value = resource
    mock_repo.update.return_value = resource
    assert service.patch_resource(uid, {}) == resource


def test_delete_resource(service, mock_repo):
    uid = uuid4()
    mock_resource = MagicMock()
    mock_repo.get_by_id.return_value = mock_resource
    mock_repo.delete.return_value = True
    assert service.delete_resource(uid) is True


def test_delete_resource_repo_error(service, mock_repo):
    uid = uuid4()
    mock_resource = MagicMock()
    mock_repo.get_by_id.return_value = mock_resource
    mock_repo.delete.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.delete_resource(uid)


def test_search_resources(service, mock_repo):
    mock_repo.search.return_value = ["r1"]
    res = service.search_resources("app")
    assert len(res) == 1
    mock_repo.search.assert_called_with(resource_name="app", limit=100)


def test_search_resources_repo_error(service, mock_repo):
    mock_repo.search.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.search_resources("test")


def test_count_resources(service, mock_repo):
    mock_repo.count.return_value = 5
    assert service.count_resources() == 5


def test_count_resources_repo_error(service, mock_repo):
    mock_repo.count.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.count_resources()


def test_activate_resource(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.activate.return_value = "active_r1"
    assert service.activate_resource(uid) == "active_r1"


def test_activate_resource_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.activate.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.activate_resource(uid)


def test_deactivate_resource(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.deactivate.return_value = "deactive_r1"
    assert service.deactivate_resource(uid) == "deactive_r1"


def test_deactivate_resource_repo_error(service, mock_repo):
    uid = uuid4()
    mock_repo.get_by_id.return_value = "r1"
    mock_repo.deactivate.side_effect = ResourcesRepositoryError("fail")
    with pytest.raises(ResourcesServiceError):
        service.deactivate_resource(uid)

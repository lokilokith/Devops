import pytest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from app.resources.models import Resource, ResourceType, ResourceStatus
from app.resources.exceptions import ResourceNotFoundError, ResourcesRepositoryError

def test_resources_repository_create_and_get(resources_repo):
    resource = Resource(
        resource_code="APP1",
        resource_name="App One",
        resource_type=ResourceType.APPLICATION,
        description="App One desc",
        status=ResourceStatus.ACTIVE
    )
    created = resources_repo.create(resource)
    assert created.id is not None
    assert created.resource_code == "APP1"

    fetched = resources_repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.resource_code == "APP1"

def test_resources_repository_get_by_code_and_name_whitespace(resources_repo, sample_resource):
    r1 = resources_repo.get_by_resource_code("  SMPL_RES  ")
    assert r1 is not None
    assert r1.id == sample_resource.id
    
    r2 = resources_repo.get_by_resource_name("  Sample Resource  ")
    assert r2 is not None
    assert r2.id == sample_resource.id

def test_resources_repository_update(resources_repo, sample_resource):
    sample_resource.resource_name = "Sample Resource Updated"
    resources_repo.update(sample_resource)
    
    fetched = resources_repo.get_by_id(sample_resource.id)
    assert fetched.resource_name == "Sample Resource Updated"

def test_resources_repository_delete(resources_repo, sample_resource):
    resources_repo.delete(sample_resource.id)
    
    fetched = resources_repo.get_by_id(sample_resource.id)
    assert fetched is None

def test_resources_repository_status_changes(resources_repo, sample_resource):
    resources_repo.deactivate(sample_resource.id)
    assert resources_repo.get_by_id(sample_resource.id).status == ResourceStatus.INACTIVE
    
    resources_repo.retire(sample_resource.id)
    assert resources_repo.get_by_id(sample_resource.id).status == ResourceStatus.RETIRED
    
    resources_repo.activate(sample_resource.id)
    assert resources_repo.get_by_id(sample_resource.id).status == ResourceStatus.ACTIVE

def test_resources_repository_list_filters(resources_repo, sample_resource):
    res2 = Resource(resource_code="LST2", resource_name="List 2", resource_type=ResourceType.DATABASE, status=ResourceStatus.INACTIVE)
    resources_repo.create(res2)
    
    all_res = resources_repo.list()
    assert len(all_res) >= 2
    
    active_res = resources_repo.list(status=ResourceStatus.ACTIVE)
    assert any(r.resource_code == "SMPL_RES" for r in active_res)
    assert all(r.status == ResourceStatus.ACTIVE for r in active_res)
    
    server_res = resources_repo.list(resource_type=ResourceType.SERVER)
    assert any(r.resource_code == "SMPL_RES" for r in server_res)
    assert all(r.resource_type == ResourceType.SERVER for r in server_res)
    
    combo_res = resources_repo.list(status=ResourceStatus.INACTIVE, resource_type=ResourceType.DATABASE)
    assert len(combo_res) >= 1
    assert any(r.resource_code == "LST2" for r in combo_res)

def test_resources_repository_count_filters(resources_repo, sample_resource):
    res2 = Resource(resource_code="CNT2", resource_name="Count 2", resource_type=ResourceType.DATABASE, status=ResourceStatus.INACTIVE)
    resources_repo.create(res2)
    
    assert resources_repo.count() >= 2
    assert resources_repo.count(status=ResourceStatus.INACTIVE) >= 1
    assert resources_repo.count(resource_type=ResourceType.DATABASE) >= 1
    assert resources_repo.count(status=ResourceStatus.INACTIVE, resource_type=ResourceType.DATABASE) >= 1

def test_resources_repository_search_filters(resources_repo, sample_resource):
    res2 = Resource(resource_code="SRCH2", resource_name="Search Two", resource_type=ResourceType.DATABASE, status=ResourceStatus.INACTIVE)
    resources_repo.create(res2)
    
    res1 = resources_repo.search(resource_name="Search", resource_code="SRCH")
    assert len(res1) == 1
    assert res1[0].resource_code == "SRCH2"
    
    res2_list = resources_repo.search(status=ResourceStatus.INACTIVE)
    assert len(res2_list) >= 1
    assert any(r.resource_code == "SRCH2" for r in res2_list)
    
    res3 = resources_repo.search(resource_type=ResourceType.DATABASE)
    assert len(res3) >= 1
    assert any(r.resource_code == "SRCH2" for r in res3)
    
    res4 = resources_repo.search(resource_code="  SRCH2  ", resource_name="  Two  ")
    assert len(res4) == 1
    assert res4[0].resource_code == "SRCH2"

def test_resources_repository_exists_whitespace(resources_repo, sample_resource):
    assert resources_repo.exists_by_resource_code("  SMPL_RES  ") is True
    assert resources_repo.exists_by_resource_name("  Sample Resource  ") is True
    assert resources_repo.exists_by_resource_code("NONEXISTENT") is False
    assert resources_repo.exists_by_resource_name("NONEXISTENT") is False

def test_resources_repository_pagination(resources_repo):
    resources_repo.create(Resource(resource_code="PAG1", resource_name="Pag 1"))
    
    res1 = resources_repo.list(limit=0)
    assert len(res1) == 1
    
    res2 = resources_repo.list(limit=2000)
    assert len(res2) >= 1
    
    res3 = resources_repo.list(offset=-10)
    assert len(res3) >= 1

def test_resources_repository_not_found_errors(resources_repo):
    missing_id = uuid4()
    with pytest.raises(ResourceNotFoundError):
        resources_repo.delete(missing_id)
    with pytest.raises(ResourceNotFoundError):
        resources_repo.activate(missing_id)

def test_resources_repository_sqlalchemy_errors(resources_repo, sample_resource):
    with patch.object(resources_repo._session, 'add', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.create(Resource(resource_code="ERR", resource_name="Error Resource"))
            
    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.get_by_id(sample_resource.id)

    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.get_by_resource_code("SMPL_RES")
            
    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.get_by_resource_name("Sample Resource")
            
    with patch.object(resources_repo._session, 'merge', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.update(sample_resource)
            
    with patch.object(resources_repo._session, 'delete', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.delete(sample_resource.id)
            
    with patch.object(resources_repo._session, 'commit', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.activate(sample_resource.id)
            
    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.exists_by_resource_code("SMPL_RES")

    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.exists_by_resource_name("Sample Resource")
            
    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.list()

    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.count()

    with patch.object(resources_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ResourcesRepositoryError):
            resources_repo.search()

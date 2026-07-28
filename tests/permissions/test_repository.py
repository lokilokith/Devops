import pytest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.permissions.exceptions import PermissionNotFoundError, PermissionsRepositoryError

def test_permissions_repository_create_and_get(permissions_repo):
    permission = Permission(
        permission_code="PERM1",
        permission_name="Perm One",
        action=PermissionAction.CREATE,
        description="Perm One desc",
        status=PermissionStatus.ACTIVE
    )
    created = permissions_repo.create(permission)
    assert created.id is not None
    assert created.permission_code == "PERM1"

    fetched = permissions_repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.permission_code == "PERM1"

def test_permissions_repository_get_by_code_and_name_whitespace(permissions_repo, sample_permission):
    p1 = permissions_repo.get_by_permission_code("  SMPL_PERM  ")
    assert p1 is not None
    assert p1.id == sample_permission.id
    
    p2 = permissions_repo.get_by_permission_name("  Sample Permission  ")
    assert p2 is not None
    assert p2.id == sample_permission.id

def test_permissions_repository_update(permissions_repo, sample_permission):
    sample_permission.permission_name = "Sample Permission Updated"
    permissions_repo.update(sample_permission)
    
    fetched = permissions_repo.get_by_id(sample_permission.id)
    assert fetched.permission_name == "Sample Permission Updated"

def test_permissions_repository_delete(permissions_repo, sample_permission):
    permissions_repo.delete(sample_permission.id)
    
    fetched = permissions_repo.get_by_id(sample_permission.id)
    assert fetched is None

def test_permissions_repository_status_changes(permissions_repo, sample_permission):
    permissions_repo.deactivate(sample_permission.id)
    assert permissions_repo.get_by_id(sample_permission.id).status == PermissionStatus.INACTIVE
    
    permissions_repo.retire(sample_permission.id)
    assert permissions_repo.get_by_id(sample_permission.id).status == PermissionStatus.RETIRED
    
    permissions_repo.activate(sample_permission.id)
    assert permissions_repo.get_by_id(sample_permission.id).status == PermissionStatus.ACTIVE

def test_permissions_repository_list_filters(permissions_repo, sample_permission):
    p2 = Permission(permission_code="LST2", permission_name="List 2", action=PermissionAction.UPDATE, status=PermissionStatus.INACTIVE)
    permissions_repo.create(p2)
    
    all_perms = permissions_repo.list()
    assert len(all_perms) >= 2
    
    active_perms = permissions_repo.list(status=PermissionStatus.ACTIVE)
    assert any(p.permission_code == "SMPL_PERM" for p in active_perms)
    assert all(p.status == PermissionStatus.ACTIVE for p in active_perms)
    
    read_perms = permissions_repo.list(action=PermissionAction.READ)
    assert any(p.permission_code == "SMPL_PERM" for p in read_perms)
    assert all(p.action == PermissionAction.READ for p in read_perms)
    
    combo_perms = permissions_repo.list(status=PermissionStatus.INACTIVE, action=PermissionAction.UPDATE)
    assert len(combo_perms) >= 1
    assert any(p.permission_code == "LST2" for p in combo_perms)

def test_permissions_repository_count_filters(permissions_repo, sample_permission):
    p2 = Permission(permission_code="CNT2", permission_name="Count 2", action=PermissionAction.UPDATE, status=PermissionStatus.INACTIVE)
    permissions_repo.create(p2)
    
    assert permissions_repo.count() >= 2
    assert permissions_repo.count(status=PermissionStatus.INACTIVE) >= 1
    assert permissions_repo.count(action=PermissionAction.UPDATE) >= 1
    assert permissions_repo.count(status=PermissionStatus.INACTIVE, action=PermissionAction.UPDATE) >= 1

def test_permissions_repository_search_filters(permissions_repo, sample_permission):
    p2 = Permission(permission_code="SRCH2", permission_name="Search Two", action=PermissionAction.UPDATE, status=PermissionStatus.INACTIVE)
    permissions_repo.create(p2)
    
    res1 = permissions_repo.search(permission_name="Search", permission_code="SRCH")
    assert len(res1) == 1
    assert res1[0].permission_code == "SRCH2"
    
    res2_list = permissions_repo.search(status=PermissionStatus.INACTIVE)
    assert len(res2_list) >= 1
    assert any(p.permission_code == "SRCH2" for p in res2_list)
    
    res3 = permissions_repo.search(action=PermissionAction.UPDATE)
    assert len(res3) >= 1
    assert any(p.permission_code == "SRCH2" for p in res3)
    
    res4 = permissions_repo.search(permission_code="  SRCH2  ", permission_name="  Two  ")
    assert len(res4) == 1
    assert res4[0].permission_code == "SRCH2"

def test_permissions_repository_exists_whitespace(permissions_repo, sample_permission):
    assert permissions_repo.exists_by_permission_code("  SMPL_PERM  ") is True
    assert permissions_repo.exists_by_permission_name("  Sample Permission  ") is True
    assert permissions_repo.exists_by_permission_code("NONEXISTENT") is False
    assert permissions_repo.exists_by_permission_name("NONEXISTENT") is False

def test_permissions_repository_pagination(permissions_repo):
    permissions_repo.create(Permission(permission_code="PAG1", permission_name="Pag 1"))
    
    res1 = permissions_repo.list(limit=0)
    assert len(res1) == 1
    
    res2 = permissions_repo.list(limit=2000)
    assert len(res2) >= 1
    
    res3 = permissions_repo.list(offset=-10)
    assert len(res3) >= 1

def test_permissions_repository_not_found_errors(permissions_repo):
    missing_id = uuid4()
    with pytest.raises(PermissionNotFoundError):
        permissions_repo.delete(missing_id)
    with pytest.raises(PermissionNotFoundError):
        permissions_repo.activate(missing_id)

def test_permissions_repository_sqlalchemy_errors(permissions_repo, sample_permission):
    with patch.object(permissions_repo._session, 'add', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.create(Permission(permission_code="ERR", permission_name="Error Permission"))
            
    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.get_by_id(sample_permission.id)

    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.get_by_permission_code("SMPL_PERM")
            
    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.get_by_permission_name("Sample Permission")
            
    with patch.object(permissions_repo._session, 'merge', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.update(sample_permission)
            
    with patch.object(permissions_repo._session, 'delete', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.delete(sample_permission.id)
            
    with patch.object(permissions_repo._session, 'commit', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.activate(sample_permission.id)
            
    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.exists_by_permission_code("SMPL_PERM")

    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.exists_by_permission_name("Sample Permission")
            
    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.list()

    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.count()

    with patch.object(permissions_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(PermissionsRepositoryError):
            permissions_repo.search()

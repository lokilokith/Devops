import pytest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError

from app.authorization.exceptions import (
    AuthorizationDeniedError,
    AuthorizationRepositoryError,
)
from app.permissions.models import PermissionAction

def test_has_permission(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    assert auth_service.has_permission(u1.id, "RES1", PermissionAction.READ) is True
    assert auth_service.has_permission(u1.id, "RES2", PermissionAction.DELETE) is True
    
    u2 = populated_db["users"]["u2"]
    assert auth_service.has_permission(u2.id, "RES1", PermissionAction.READ) is False
    assert auth_service.has_permission(u2.id, "RES2", PermissionAction.DELETE) is True

def test_authorize(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    auth_service.authorize(u1.id, "RES1", PermissionAction.READ)
    
    u2 = populated_db["users"]["u2"]
    with pytest.raises(AuthorizationDeniedError):
        auth_service.authorize(u2.id, "RES1", PermissionAction.READ)

def test_get_user_permissions(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    perms = auth_service.get_user_permissions(u1.id)
    assert len(perms) == 2
    
    u2 = populated_db["users"]["u2"]
    perms = auth_service.get_user_permissions(u2.id)
    assert len(perms) == 1
    
    u3 = populated_db["users"]["u3"]
    perms = auth_service.get_user_permissions(u3.id)
    assert len(perms) == 0

def test_get_user_roles(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    roles = auth_service.get_user_roles(u1.id)
    assert len(roles) == 2
    
    u3 = populated_db["users"]["u3"]
    roles = auth_service.get_user_roles(u3.id)
    assert len(roles) == 0

def test_get_accessible_resources(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    resources = auth_service.get_accessible_resources(u1.id)
    assert len(resources) == 2
    
    u2 = populated_db["users"]["u2"]
    resources = auth_service.get_accessible_resources(u2.id)
    assert len(resources) == 1
    assert resources[0].resource_code == "RES2"
    
    u3 = populated_db["users"]["u3"]
    resources = auth_service.get_accessible_resources(u3.id)
    assert len(resources) == 0

def test_unknown_user_resource_permission(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    assert auth_service.has_permission(uuid4(), "RES1", PermissionAction.READ) is False
    assert auth_service.has_permission(u1.id, "UNKNOWN", PermissionAction.READ) is False
    assert auth_service.has_permission(u1.id, "RES1", PermissionAction.EXECUTE) is False

def test_sqlalchemy_errors(auth_service, populated_db):
    u1 = populated_db["users"]["u1"]
    with patch.object(auth_service._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(AuthorizationRepositoryError):
            auth_service.has_permission(u1.id, "RES1", PermissionAction.READ)
            
    with patch.object(auth_service._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(AuthorizationRepositoryError):
            auth_service.get_user_permissions(u1.id)
            
    with patch.object(auth_service._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(AuthorizationRepositoryError):
            auth_service.get_user_roles(u1.id)
            
    with patch.object(auth_service._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(AuthorizationRepositoryError):
            auth_service.get_accessible_resources(u1.id)

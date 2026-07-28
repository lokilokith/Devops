import pytest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError

from app.user_roles.exceptions import (
    UserRoleAlreadyExistsError,
    UserRoleNotFoundError,
    UserRolesRepositoryError,
)
from app.roles.models import Role, RoleType, RoleStatus
from app.identity.models import User, UserStatus

def test_assign_role_to_user(user_roles_repo, sample_user, sample_role):
    ur = user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)
    assert ur.user_id == sample_user.id
    assert ur.role_id == sample_role.id
    assert user_roles_repo.exists(sample_user.id, sample_role.id) is True

def test_assign_role_already_exists(user_roles_repo, sample_user, sample_role):
    user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)
    with pytest.raises(UserRoleAlreadyExistsError):
        user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)

def test_remove_role_from_user(user_roles_repo, sample_user, sample_role):
    user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)
    assert user_roles_repo.exists(sample_user.id, sample_role.id) is True
    
    user_roles_repo.remove_role_from_user(sample_user.id, sample_role.id)
    assert user_roles_repo.exists(sample_user.id, sample_role.id) is False

def test_remove_role_not_found(user_roles_repo, sample_user, sample_role):
    with pytest.raises(UserRoleNotFoundError):
        user_roles_repo.remove_role_from_user(sample_user.id, sample_role.id)

def test_get_assignment(user_roles_repo, sample_user, sample_role):
    assert user_roles_repo.get_assignment(sample_user.id, sample_role.id) is None
    ur = user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)
    assert user_roles_repo.get_assignment(sample_user.id, sample_role.id).user_id == ur.user_id

def test_list_roles_for_user(user_roles_repo, sample_user, db_session):
    r1 = Role(role_code="ROL1", role_name="Role 1", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    r2 = Role(role_code="ROL2", role_name="Role 2", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    db_session.add_all([r1, r2])
    db_session.commit()
    
    user_roles_repo.assign_role_to_user(sample_user.id, r1.id)
    user_roles_repo.assign_role_to_user(sample_user.id, r2.id)
    
    roles = user_roles_repo.list_roles_for_user(sample_user.id)
    assert len(roles) == 2
    assert {r.role_code for r in roles} == {"ROL1", "ROL2"}

def test_list_users_for_role(user_roles_repo, sample_role, db_session):
    u1 = User(employee_id="U1", username="usr1", email="usr1@e.com", full_name="u1")
    u2 = User(employee_id="U2", username="usr2", email="usr2@e.com", full_name="u2")
    db_session.add_all([u1, u2])
    db_session.commit()
    
    user_roles_repo.assign_role_to_user(u1.id, sample_role.id)
    user_roles_repo.assign_role_to_user(u2.id, sample_role.id)
    
    users = user_roles_repo.list_users_for_role(sample_role.id)
    assert len(users) == 2
    assert {u.username for u in users} == {"usr1", "usr2"}

def test_count_roles_for_user(user_roles_repo, sample_user, db_session):
    r1 = Role(role_code="COL1", role_name="C1", role_type=RoleType.SYSTEM, status=RoleStatus.ACTIVE)
    db_session.add(r1)
    db_session.commit()
    
    user_roles_repo.assign_role_to_user(sample_user.id, r1.id)
    assert user_roles_repo.count_roles_for_user(sample_user.id) == 1

def test_count_users_for_role(user_roles_repo, sample_role, db_session):
    u1 = User(employee_id="CU1", username="cusr1", email="cusr1@e.com", full_name="u1")
    db_session.add(u1)
    db_session.commit()
    
    user_roles_repo.assign_role_to_user(u1.id, sample_role.id)
    assert user_roles_repo.count_users_for_role(sample_role.id) == 1

def test_sqlalchemy_errors(user_roles_repo, sample_user, sample_role):
    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.get_assignment(sample_user.id, sample_role.id)
            
    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.exists(sample_user.id, sample_role.id)

    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.list_roles_for_user(sample_user.id)
            
    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.list_users_for_role(sample_role.id)

    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.count_roles_for_user(sample_user.id)
            
    with patch.object(user_roles_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.count_users_for_role(sample_role.id)

def test_assign_role_error_after_exists(user_roles_repo, sample_user, sample_role):
    with patch.object(user_roles_repo._session, 'add', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)

def test_remove_role_error_after_fetch(user_roles_repo, sample_user, sample_role):
    user_roles_repo.assign_role_to_user(sample_user.id, sample_role.id)
    with patch.object(user_roles_repo._session, 'delete', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(UserRolesRepositoryError):
            user_roles_repo.remove_role_from_user(sample_user.id, sample_role.id)

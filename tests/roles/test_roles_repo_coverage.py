import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.roles.exceptions import RolesRepositoryError
from app.roles.models import RoleStatus
from app.roles.repository import RolesRepository


def test_roles_repo_set_status_sqlalchemy_error():
    session = MagicMock()
    repo = RolesRepository(session)
    repo._get_role_or_raise = MagicMock()
    repo._commit_and_refresh = MagicMock(side_effect=SQLAlchemyError("test"))

    with pytest.raises(RolesRepositoryError):
        repo._update_status(uuid.uuid4(), RoleStatus.ACTIVE)

    session.rollback.assert_called_once()


def test_roles_repo_delete_sqlalchemy_error():
    session = MagicMock()
    repo = RolesRepository(session)
    repo._get_role_or_raise = MagicMock()
    session.delete.side_effect = SQLAlchemyError("test")

    with pytest.raises(RolesRepositoryError):
        repo.delete(uuid.uuid4())

    session.rollback.assert_called_once()

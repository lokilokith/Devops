import uuid
from unittest.mock import MagicMock

from app.vault.repository import SqlAlchemyVaultRepository


def test_vault_repository_exists():
    session = MagicMock()
    repo = SqlAlchemyVaultRepository(session)
    session.execute.return_value.scalar_one_or_none.return_value = uuid.uuid4()
    assert repo.exists(uuid.uuid4()) is True

    session.execute.return_value.scalar_one_or_none.return_value = None
    assert repo.exists(uuid.uuid4()) is False


def test_vault_repository_delete():
    session = MagicMock()
    repo = SqlAlchemyVaultRepository(session)
    model = MagicMock()
    session.get.return_value = model
    repo.delete(uuid.uuid4())
    session.delete.assert_called_once_with(model)
    session.flush.assert_called_once()


def test_vault_repository_delete_not_found():
    session = MagicMock()
    repo = SqlAlchemyVaultRepository(session)
    session.get.return_value = None
    repo.delete(uuid.uuid4())
    session.delete.assert_not_called()


def test_vault_repository_list_active_secrets():
    session = MagicMock()
    repo = SqlAlchemyVaultRepository(session)
    repo._to_domain = MagicMock(return_value="domain")
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        "model1",
        "model2",
    ]
    res = repo.list_active_secrets()
    assert res == ["domain", "domain"]


def test_vault_repository_count_by_status():
    session = MagicMock()
    repo = SqlAlchemyVaultRepository(session)
    session.execute.return_value.scalar_one.return_value = 5
    res = repo.count_by_status("ACTIVE")
    assert res == 5

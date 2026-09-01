import uuid
from unittest.mock import MagicMock

from app.vault_lifecycle.repository import SecretRotationPolicyRepository


def test_secret_rotation_policy_repo_find_by_id():
    session = MagicMock()
    repo = SecretRotationPolicyRepository(session)
    repo.find_by_id(uuid.uuid4())
    session.execute.assert_called_once()
    session.execute.return_value.scalar_one_or_none.assert_called_once()


def test_secret_rotation_policy_repo_delete():
    session = MagicMock()
    repo = SecretRotationPolicyRepository(session)
    policy = MagicMock()
    repo.delete(policy)
    session.delete.assert_called_once_with(policy)
    session.flush.assert_called_once()

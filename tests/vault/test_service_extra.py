"""Unit tests for VaultApplicationService edge cases and RBAC denials."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault.service import VaultApplicationService


def test_create_secret_rbac_denied():
    repo = MagicMock()
    enc_svc = MagicMock()
    domain_svc = MagicMock()
    authz = MagicMock()
    authz.authorize.side_effect = AuthorizationDeniedError("Denied")
    audit = MagicMock()
    policy_engine = MagicMock()
    session = MagicMock()

    service = VaultApplicationService(
        domain_svc, enc_svc, repo, policy_engine, audit, authz, session
    )
    actor_id = uuid4()
    res_id = uuid4()

    with pytest.raises(AuthorizationDeniedError):
        service.create_secret(actor_id, res_id, b"secret")

    assert audit.log_event.called is True


def test_rotate_secret_rbac_denied():
    repo = MagicMock()
    enc_svc = MagicMock()
    domain_svc = MagicMock()
    authz = MagicMock()
    authz.authorize.side_effect = AuthorizationDeniedError("Denied")
    audit = MagicMock()
    policy_engine = MagicMock()
    session = MagicMock()

    service = VaultApplicationService(
        domain_svc, enc_svc, repo, policy_engine, audit, authz, session
    )
    actor_id = uuid4()
    secret_id = uuid4()

    with pytest.raises(AuthorizationDeniedError):
        service.rotate_secret(actor_id, secret_id, b"new_secret")

    assert audit.log_event.called is True


def test_disable_secret_rbac_denied():
    repo = MagicMock()
    enc_svc = MagicMock()
    domain_svc = MagicMock()
    authz = MagicMock()
    authz.authorize.side_effect = AuthorizationDeniedError("Denied")
    audit = MagicMock()
    policy_engine = MagicMock()
    session = MagicMock()

    service = VaultApplicationService(
        domain_svc, enc_svc, repo, policy_engine, audit, authz, session
    )
    actor_id = uuid4()
    secret_id = uuid4()

    with pytest.raises(AuthorizationDeniedError):
        service.disable_secret(actor_id, secret_id)

    assert audit.log_event.called is True


def test_delete_secret_rbac_denied():
    repo = MagicMock()
    enc_svc = MagicMock()
    domain_svc = MagicMock()
    authz = MagicMock()
    authz.authorize.side_effect = AuthorizationDeniedError("Denied")
    audit = MagicMock()
    policy_engine = MagicMock()
    session = MagicMock()

    service = VaultApplicationService(
        domain_svc, enc_svc, repo, policy_engine, audit, authz, session
    )
    actor_id = uuid4()
    secret_id = uuid4()

    with pytest.raises(AuthorizationDeniedError):
        service.delete_secret(actor_id, secret_id)

    assert audit.log_event.called is True

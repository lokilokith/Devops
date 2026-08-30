"""Tests for Policy Engine Service and Evaluation Logic."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.policy_engine.models import AccessPolicy, PolicyEffect
from app.policy_engine.repository import PolicyRepository
from app.policy_engine.service import PolicyService


@pytest.fixture
def policy_service(db_session):
    repo = PolicyRepository(db_session)
    mock_auth = MagicMock()
    mock_audit = MagicMock()
    return PolicyService(repo, mock_auth, mock_audit)


def test_evaluation_missing_rbac(policy_service):
    policy_service._auth_service.has_permission.return_value = False

    res = policy_service.evaluate_policy(uuid4(), "res-123", "read", {})

    assert res["decision"] == "DENY"
    assert "RBAC permission missing" in res["reason"]
    policy_service._audit_service.log_event.assert_called_once()


def test_evaluation_valid_rbac_no_abac(policy_service):
    policy_service._auth_service.has_permission.return_value = True

    res = policy_service.evaluate_policy(uuid4(), "res-123", "read", {})

    assert res["decision"] == "ALLOW"
    assert "no active ABAC policies" in res["reason"]


def test_evaluation_ip_mismatch_denies(policy_service):
    policy_service._auth_service.has_permission.return_value = True

    policy_service._repo.create(
        AccessPolicy(
            name="Internal IP Only",
            conditions={"allowed_ip_ranges": ["10.0.0.0/8"]},
            effect=PolicyEffect.ALLOW,
        )
    )

    res = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"ip": "192.168.1.5"}
    )
    assert res["decision"] == "DENY"
    assert "matched no ALLOW policies" in res["reason"]

    res2 = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"ip": "10.0.0.5"}
    )
    assert res2["decision"] == "ALLOW"
    assert "ALLOW by policy" in res2["reason"]


def test_evaluation_time_restriction(policy_service):
    policy_service._auth_service.has_permission.return_value = True

    policy_service._repo.create(
        AccessPolicy(
            name="Working Hours",
            conditions={"allowed_hours": {"start": "09:00", "end": "18:00"}},
            effect=PolicyEffect.ALLOW,
        )
    )

    res_deny = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"time": "2023-01-01T22:00:00Z"}
    )
    assert res_deny["decision"] == "DENY"

    res_allow = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"time": "2023-01-01T12:00:00Z"}
    )
    assert res_allow["decision"] == "ALLOW"


def test_evaluation_explicit_deny_wins(policy_service):
    policy_service._auth_service.has_permission.return_value = True

    # ALLOW for 10.0.0.0/8
    policy_service._repo.create(
        AccessPolicy(
            name="Allow Internal",
            conditions={"allowed_ip_ranges": ["10.0.0.0/8"]},
            effect=PolicyEffect.ALLOW,
            priority=10,
        )
    )
    # DENY for a specific malicious IP within internal
    policy_service._repo.create(
        AccessPolicy(
            name="Deny Malicious",
            conditions={"allowed_ip_ranges": ["10.0.0.5/32"]},
            effect=PolicyEffect.DENY,
            priority=100,
        )
    )

    res_allow = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"ip": "10.0.0.6"}
    )
    assert res_allow["decision"] == "ALLOW"

    res_deny = policy_service.evaluate_policy(
        uuid4(), "res-123", "read", {"ip": "10.0.0.5"}
    )
    assert res_deny["decision"] == "DENY"
    assert "Explicit DENY by policy" in res_deny["reason"]


def test_evaluation_role_restriction(policy_service):
    policy_service._auth_service.has_permission.return_value = True

    mock_role = MagicMock()
    mock_role.role_code = "SECURITY_ADMIN"
    policy_service._auth_service.get_user_roles.return_value = [mock_role]

    policy_service._repo.create(
        AccessPolicy(
            name="Sec Admin Only",
            conditions={"allowed_roles": ["SECURITY_ADMIN"]},
            effect=PolicyEffect.ALLOW,
        )
    )

    res_allow = policy_service.evaluate_policy(uuid4(), "res-123", "read", {})
    assert res_allow["decision"] == "ALLOW"

    # Change user role to Help Desk
    mock_role.role_code = "HELP_DESK"
    policy_service._auth_service.get_user_roles.return_value = [mock_role]

    res_deny = policy_service.evaluate_policy(uuid4(), "res-123", "read", {})
    assert res_deny["decision"] == "DENY"

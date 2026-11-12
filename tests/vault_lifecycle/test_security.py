"""Security tests for Vault Lifecycle."""

import uuid
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def auth_headers(normal_token):
    return {"Authorization": f"Bearer {normal_token}"}


def test_idor_get_policy(client, normal_token):
    # A user tries to get a policy they shouldn't have access to
    policy_id = str(uuid.uuid4())
    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # Simulate authz denial
        from app.authorization.exceptions import AuthorizationDeniedError

        mock_service.get_policy.side_effect = AuthorizationDeniedError("Denied")

        response = client.get(
            f"/vault-lifecycle/policies/{policy_id}",
            headers={"Authorization": f"Bearer {normal_token}"},
        )
        assert response.status_code == 403


def test_malformed_uuid(client, normal_token):
    response = client.get(
        "/vault-lifecycle/policies/not-a-uuid",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert response.status_code == 404  # Flask routing handles invalid UUIDs as 404


def test_malformed_interval_negative(client, normal_token):
    payload = {"vault_secret_id": str(uuid.uuid4()), "rotation_interval_seconds": -500}
    response = client.post(
        "/vault-lifecycle/policies",
        json=payload,
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert response.status_code == 400


def test_no_plaintext_leakage_in_response(client, auth_headers):
    # Vault lifecycle policies should never return secret payloads
    policy_id = str(uuid.uuid4())

    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy

        mock_policy = SecretRotationPolicy(
            id=uuid.UUID(policy_id),
            vault_secret_id=uuid.uuid4(),
            rotation_interval_seconds=3600,
            status=RotationStatus.ACTIVE,
        )
        mock_service.get_policy.return_value = mock_policy

        response = client.get(
            f"/vault-lifecycle/policies/{policy_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data_str = str(response.json)
        assert "payload" not in data_str.lower()
        assert "plaintext" not in data_str.lower()

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, Mock

import pytest
from werkzeug.exceptions import Forbidden

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault_lifecycle.exceptions import PolicyNotFoundError, PolicyValidationError
from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus
from app.vault_lifecycle.engine import RotationEligibilityStatus


@pytest.fixture
def auth_headers(normal_token):
    return {"Authorization": f"Bearer {normal_token}"}


def test_create_policy_route(client, auth_headers):
    vault_secret_id = str(uuid.uuid4())
    payload = {
        "vault_secret_id": vault_secret_id,
        "rotation_interval_seconds": 3600
    }

    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_policy = SecretRotationPolicy(
            id=uuid.uuid4(),
            vault_secret_id=uuid.UUID(vault_secret_id),
            rotation_interval_seconds=3600,
            status=RotationStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        mock_service.create_policy.return_value = mock_policy
        
        response = client.post(
            "/vault-lifecycle/policies",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        assert response.json["data"]["id"] == str(mock_policy.id)
        assert response.json["data"]["rotation_interval_seconds"] == 3600


def test_create_policy_validation_error(client, auth_headers):
    vault_secret_id = str(uuid.uuid4())
    payload = {
        "vault_secret_id": vault_secret_id,
        "rotation_interval_seconds": 30  # Invalid, min 60
    }

    with patch("app.vault_lifecycle.routes.get_lifecycle_service"):
        response = client.post(
            "/vault-lifecycle/policies",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 400


def test_get_policy_route(client, auth_headers):
    policy_id = str(uuid.uuid4())
    
    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_policy = SecretRotationPolicy(
            id=uuid.UUID(policy_id),
            vault_secret_id=uuid.uuid4(),
            rotation_interval_seconds=3600,
            status=RotationStatus.ACTIVE
        )
        mock_service.get_policy.return_value = mock_policy
        
        response = client.get(
            f"/vault-lifecycle/policies/{policy_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json["data"]["rotation_interval_seconds"] == 3600


def test_get_policy_not_found(client, auth_headers):
    policy_id = str(uuid.uuid4())
    
    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_service.get_policy.side_effect = PolicyNotFoundError("Not found")
        
        response = client.get(
            f"/vault-lifecycle/policies/{policy_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 404


def test_evaluate_secret_route(client, auth_headers):
    secret_id = str(uuid.uuid4())
    
    with patch("app.vault_lifecycle.routes.get_lifecycle_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_service.evaluate_secret.return_value = {
            "status": RotationEligibilityStatus.DUE,
            "reason": "Due",
            "next_rotation_at": None
        }
        
        response = client.post(
            f"/vault-lifecycle/secrets/{secret_id}/evaluate",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json["data"]["status"] == "DUE"

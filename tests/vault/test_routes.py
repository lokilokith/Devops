import uuid
from unittest.mock import patch, Mock

import pytest
from werkzeug.exceptions import Forbidden

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault.service import ApprovalRequiredError
from app.vault.domain import Secret, SecretVersion, SecretMetadata


@pytest.fixture
def auth_headers(normal_token):
    return {"Authorization": f"Bearer {normal_token}"}


def test_create_secret_route(client, auth_headers):
    resource_id = str(uuid.uuid4())
    payload = "my-secret-payload"

    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_secret = Mock(spec=Secret)
        mock_secret.id = uuid.uuid4()
        mock_secret.resource_id = uuid.UUID(resource_id)
        mock_secret.status = "ACTIVE"
        mock_secret.created_at = "2026-01-01T00:00:00Z"
        
        mock_service.create_secret.return_value = mock_secret
        
        response = client.post(
            "/vault/secrets",
            json={"resource_id": resource_id, "payload": payload},
            headers=auth_headers
        )
        
        assert response.status_code == 201
        assert response.json["id"] == str(mock_secret.id)


def test_retrieve_secret_route_success(client, auth_headers):
    secret_id = str(uuid.uuid4())
    
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_service.retrieve_secret.return_value = b"decrypted-payload"
        
        mock_secret = Mock()
        mock_secret.id = uuid.UUID(secret_id)
        mock_version = Mock()
        mock_version.created_at = "2026-01-01T00:00:00Z"
        mock_version.metadata.key_version = "v1"
        mock_version.metadata.algorithm = "AES-256-GCM"
        mock_secret.get_current_version.return_value = mock_version
        
        mock_service._repository.get_by_id.return_value = mock_secret
        
        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json["payload"] == "decrypted-payload"
        assert response.json["metadata"]["algorithm"] == "AES-256-GCM"


def test_retrieve_secret_route_approval_required(client, auth_headers):
    secret_id = str(uuid.uuid4())
    resource_id = str(uuid.uuid4())
    
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_service.retrieve_secret.side_effect = ApprovalRequiredError(uuid.UUID(resource_id))
        
        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve",
            headers=auth_headers
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code} with {response.json}"
        assert response.json.get("error") == "APPROVAL_REQUIRED", f"Failed: {response.json}"
        assert response.json["resource_id"] == resource_id


def test_retrieve_secret_route_denied(client, auth_headers):
    secret_id = str(uuid.uuid4())
    
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        
        mock_service.retrieve_secret.side_effect = AuthorizationDeniedError("Nope")
        
        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve",
            headers=auth_headers
        )
        
        assert response.status_code == 403

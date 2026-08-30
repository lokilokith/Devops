import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, PropertyMock, patch

import pytest

from app.authorization.exceptions import AuthorizationDeniedError
from app.vault.domain import Secret
from app.vault.service import ApprovalRequiredError


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
        type(mock_secret).id = PropertyMock(return_value=uuid.uuid4())
        type(mock_secret).resource_id = PropertyMock(
            return_value=uuid.UUID(resource_id)
        )
        mock_secret.status = "ACTIVE"
        mock_secret.created_at = datetime.now(timezone.utc)

        mock_service.create_secret.return_value = mock_secret

        response = client.post(
            "/vault/secrets",
            json={"resource_id": resource_id, "payload": payload},
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json["data"]["id"] == str(mock_secret.id)


def test_retrieve_secret_route_success(client, auth_headers):
    secret_id = str(uuid.uuid4())

    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        mock_service.retrieve_secret.return_value = b"decrypted-payload"

        mock_secret = Mock()
        type(mock_secret).id = PropertyMock(return_value=uuid.UUID(secret_id))
        mock_version = Mock()
        mock_version.created_at = datetime.now(timezone.utc)
        mock_version.metadata.key_version = "v1"
        mock_version.metadata.algorithm = "AES-256-GCM"
        mock_secret.get_current_version.return_value = mock_version

        mock_service._repository.find_by_id.return_value = mock_secret

        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json["data"]["payload"] == "decrypted-payload"
        assert response.json["data"]["metadata"]["algorithm"] == "AES-256-GCM"


def test_retrieve_secret_route_approval_required(client, auth_headers):
    secret_id = str(uuid.uuid4())
    resource_id = str(uuid.uuid4())

    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        mock_service.retrieve_secret.side_effect = ApprovalRequiredError(
            uuid.UUID(resource_id)
        )

        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve", headers=auth_headers
        )

        assert (
            response.status_code == 403
        ), f"Expected 403, got {response.status_code} with {response.json}"
        assert (
            response.json.get("error") == "APPROVAL_REQUIRED"
        ), f"Failed: {response.json}"
        assert response.json["resource_id"] == resource_id


def test_retrieve_secret_route_denied(client, auth_headers):
    secret_id = str(uuid.uuid4())

    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        mock_service.retrieve_secret.side_effect = AuthorizationDeniedError("Nope")

        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve", headers=auth_headers
        )

        assert response.status_code == 403


def test_list_secrets_route(client, auth_headers):
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.list_secrets.return_value = []
        response = client.get("/vault/secrets", headers=auth_headers)
        assert response.status_code == 200


def test_list_secrets_authz_error(client, auth_headers):
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.list_secrets.side_effect = AuthorizationDeniedError("Nope")
        response = client.get("/vault/secrets", headers=auth_headers)
        assert response.status_code == 403


def test_create_secret_value_error(client, auth_headers):
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        response = client.post(
            "/vault/secrets",
            json={"resource_id": "invalid-uuid", "payload": "payload"},
            headers=auth_headers,
        )
        assert response.status_code == 400


def test_create_secret_authz_error(client, auth_headers):
    resource_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.create_secret.side_effect = AuthorizationDeniedError("Nope")
        response = client.post(
            "/vault/secrets",
            json={"resource_id": resource_id, "payload": "payload"},
            headers=auth_headers,
        )
        assert response.status_code == 403


def test_delete_secret_success(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        response = client.delete(f"/vault/secrets/{secret_id}", headers=auth_headers)
        assert response.status_code == 200


def test_delete_secret_not_found(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.delete_secret.side_effect = ValueError("secret not found")
        response = client.delete(f"/vault/secrets/{secret_id}", headers=auth_headers)
        assert response.status_code == 404


def test_delete_secret_authz_error(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.delete_secret.side_effect = AuthorizationDeniedError("Nope")
        response = client.delete(f"/vault/secrets/{secret_id}", headers=auth_headers)
        assert response.status_code == 403


def test_retrieve_secret_value_error(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.retrieve_secret.side_effect = ValueError("secret not found")
        response = client.post(
            f"/vault/secrets/{secret_id}/retrieve", headers=auth_headers
        )
        assert response.status_code == 404


def test_rotate_secret_success(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        mock_secret = Mock()
        type(mock_secret).id = PropertyMock(return_value=uuid.UUID(secret_id))
        mock_secret.status = "ACTIVE"
        mock_secret.created_at = datetime.now(timezone.utc)
        mock_service.rotate_secret.return_value = mock_secret

        response = client.post(
            f"/vault/secrets/{secret_id}/rotate",
            json={"resource_id": str(uuid.uuid4()), "payload": "new-payload"},
            headers=auth_headers,
        )
        assert response.status_code == 200


def test_rotate_secret_authz_error(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.rotate_secret.side_effect = AuthorizationDeniedError("Nope")
        response = client.post(
            f"/vault/secrets/{secret_id}/rotate",
            json={"resource_id": str(uuid.uuid4()), "payload": "new-payload"},
            headers=auth_headers,
        )
        assert response.status_code == 403


def test_disable_secret_success(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        mock_secret = Mock()
        type(mock_secret).id = PropertyMock(return_value=uuid.UUID(secret_id))
        mock_secret.status = "DISABLED"
        mock_secret.created_at = datetime.now(timezone.utc)
        mock_service.disable_secret.return_value = mock_secret

        response = client.post(
            f"/vault/secrets/{secret_id}/disable", headers=auth_headers
        )
        assert response.status_code == 200


def test_disable_secret_not_found(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.disable_secret.side_effect = ValueError("secret not found")
        response = client.post(
            f"/vault/secrets/{secret_id}/disable", headers=auth_headers
        )
        assert response.status_code == 404


def test_disable_secret_authz_error(client, auth_headers):
    secret_id = str(uuid.uuid4())
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.disable_secret.side_effect = AuthorizationDeniedError("Nope")
        response = client.post(
            f"/vault/secrets/{secret_id}/disable", headers=auth_headers
        )
        assert response.status_code == 403


def test_vault_stats_success(client, auth_headers):
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.get_statistics.return_value = {
            "total_secrets": 1,
            "active_secrets": 1,
        }
        response = client.get("/vault/secrets/stats", headers=auth_headers)
        assert response.status_code == 200


def test_vault_stats_authz_error(client, auth_headers):
    with patch("app.vault.routes.get_vault_service") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service
        mock_service.get_statistics.side_effect = AuthorizationDeniedError("Nope")
        response = client.get("/vault/secrets/stats", headers=auth_headers)
        assert response.status_code == 403

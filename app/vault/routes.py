"""Vault API Routes."""

from __future__ import annotations

import uuid
import json

from flask import request, g
from flask_restx import Resource, marshal
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from app.api.decorators import login_required
from app.api.responses import success_response
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.exceptions import AuthorizationDeniedError
from app.authorization.service import AuthorizationService
from app.extensions import db
from app.policy_engine.engine import PolicyEngine
from app.vault.crypto import EncryptionService, LocalKMSProvider
from app.vault.kms_factory import KMSProviderFactory
from app.vault.domain import SecretDomainService
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault.schemas import (
    secret_create_dto,
    secret_response_dto,
    secret_reveal_dto,
    vault_statistics_dto,
    vault_secret_response_wrapper,
    vault_secret_list_wrapper,
    vault_stats_wrapper,
    vault_reveal_wrapper,
    vault_ns,
)
from app.vault.service import ApprovalRequiredError, VaultApplicationService
from flask_restx import marshal


def get_vault_service() -> VaultApplicationService:
    return VaultApplicationService(
        domain_service=SecretDomainService(),
        encryption_service=EncryptionService(KMSProviderFactory.resolve_active_provider(db.session)),
        repository=SqlAlchemyVaultRepository(db.session),
        policy_engine=PolicyEngine(db.session, AuthorizationService(db.session)),
        audit_service=AuditService(AuditRepository(db.session)),
        authz_service=AuthorizationService(db.session),
        session=db.session,
    )


@vault_ns.route("/secrets")
class SecretCollection(Resource):
    @vault_ns.response(200, "Success", vault_secret_list_wrapper)
    @login_required
    def get(self):
        """List active secrets."""
        service = get_vault_service()
        try:
            secrets = service.list_secrets(actor_id=uuid.UUID(g.user_id))
            data = marshal(secrets, secret_response_dto)
            return success_response(data=data, status_code=200)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))

    @vault_ns.expect(secret_create_dto, validate=True)
    @vault_ns.response(201, "Created", vault_secret_response_wrapper)
    @login_required
    def post(self):
        """Create a new secret."""
        data = request.json
        try:
            resource_id = uuid.UUID(data["resource_id"])
        except ValueError:
            raise BadRequest("Invalid resource_id format.")

        payload_bytes = data["payload"].encode("utf-8")

        service = get_vault_service()
        try:
            secret = service.create_secret(
                actor_id=uuid.UUID(g.user_id),
                resource_id=resource_id,
                plaintext=payload_bytes
            )
            data = marshal(secret, secret_response_dto)
            return success_response(data=data, status_code=201)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))


@vault_ns.route("/secrets/<uuid:secret_id>")
class SecretItem(Resource):
    @login_required
    def delete(self, secret_id):
        """Delete (tombstone) a secret."""
        service = get_vault_service()
        try:
            service.delete_secret(uuid.UUID(g.user_id), secret_id)
            return success_response("Secret deleted successfully", 200)
        except ValueError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise BadRequest(str(e))
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))


@vault_ns.route("/secrets/<uuid:secret_id>/retrieve")
class SecretReveal(Resource):
    @vault_ns.response(200, "Success", vault_reveal_wrapper)
    @login_required
    def post(self, secret_id):
        """Retrieve and decrypt the secret payload."""
        service = get_vault_service()
        try:
            plaintext_bytes = service.retrieve_secret(uuid.UUID(g.user_id), secret_id)

            secret = service._repository.find_by_id(secret_id)
            version = secret.get_current_version()

            data = marshal({
                "id": str(secret.id),
                "payload": plaintext_bytes.decode("utf-8"),
                "metadata": {
                    "key_version": version.metadata.key_version,
                    "algorithm": version.metadata.algorithm,
                    "created_at": version.created_at
                }
            }, secret_reveal_dto)
            
            return success_response(data=data, status_code=200)

        except ApprovalRequiredError as e:
            # 403 response mapped precisely to user's requested payload
            return {
                "error": "APPROVAL_REQUIRED",
                "message": "Vault access requires approval",
                "resource_id": str(e.resource_id),
                "request_action": "CREATE_ACCESS_REQUEST"
            }, 403
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))
        except ValueError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise BadRequest(str(e))


@vault_ns.route("/secrets/<uuid:secret_id>/rotate")
class SecretRotate(Resource):
    @vault_ns.expect(secret_create_dto, validate=True)
    @vault_ns.response(200, "Success", vault_secret_response_wrapper)
    @login_required
    def post(self, secret_id):
        """Rotate a secret."""
        data = request.json
        payload_bytes = data["payload"].encode("utf-8")

        service = get_vault_service()
        try:
            secret = service.rotate_secret(
                actor_id=uuid.UUID(g.user_id),
                secret_id=secret_id,
                new_plaintext=payload_bytes
            )
            data_resp = marshal(secret, secret_response_dto)
            return success_response(data=data_resp, status_code=200)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))
        except ValueError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise BadRequest(str(e))


@vault_ns.route("/secrets/<uuid:secret_id>/disable")
class SecretDisable(Resource):
    @vault_ns.response(200, "Success", vault_secret_response_wrapper)
    @login_required
    def post(self, secret_id):
        """Disable a secret."""
        service = get_vault_service()
        try:
            secret = service.disable_secret(uuid.UUID(g.user_id), secret_id)
            data_resp = marshal(secret, secret_response_dto)
            return success_response(data=data_resp, status_code=200)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))
        except ValueError as e:
            if "not found" in str(e).lower():
                raise NotFound(str(e))
            raise BadRequest(str(e))


@vault_ns.route("/secrets/stats")
class VaultStatistics(Resource):
    @vault_ns.response(200, "Success", vault_stats_wrapper)
    @login_required
    def get(self):
        """Get vault statistics."""
        service = get_vault_service()
        try:
            stats = service.get_statistics(actor_id=uuid.UUID(g.user_id))
            data_resp = marshal(stats, vault_statistics_dto)
            return success_response(data=data_resp, status_code=200)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))


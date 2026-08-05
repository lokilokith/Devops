"""Vault DTO Schemas."""

from __future__ import annotations

from flask_restx import Namespace, fields

# We define the Vault Namespace here to attach models easily.
vault_ns = Namespace("vault", description="Credential Vault operations")

secret_create_dto = vault_ns.model(
    "SecretCreate",
    {
        "resource_id": fields.String(required=True, description="Phase 0 Resource UUID"),
        "payload": fields.String(required=True, description="The plaintext secret material"),
    },
)

secret_metadata_dto = vault_ns.model(
    "SecretMetadata",
    {
        "key_version": fields.String(description="The Master Key version identifier"),
        "algorithm": fields.String(description="The encryption algorithm used"),
        "created_at": fields.DateTime(description="Creation time of the version"),
    },
)

secret_response_dto = vault_ns.model(
    "SecretResponse",
    {
        "id": fields.String(description="Secret UUID"),
        "resource_id": fields.String(description="Phase 0 Resource UUID"),
        "status": fields.String(description="Current status (e.g., ACTIVE, DISABLED)"),
        "created_at": fields.DateTime(description="Creation timestamp"),
    },
)

secret_reveal_dto = vault_ns.model(
    "SecretReveal",
    {
        "id": fields.String(description="Secret UUID"),
        "payload": fields.String(description="The decrypted plaintext payload over TLS"),
        "metadata": fields.Nested(secret_metadata_dto),
    },
)

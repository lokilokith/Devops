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

resource_nested_dto = vault_ns.model(
    "NestedResource",
    {
        "id": fields.String(description="Resource UUID"),
        "resource_name": fields.String(description="Resource Name"),
        "resource_code": fields.String(description="Resource Code"),
        "resource_type": fields.String(description="Resource Type"),
    }
)

secret_response_dto = vault_ns.model(
    "SecretResponse",
    {
        "id": fields.String(description="Secret UUID"),
        "resource_id": fields.String(description="Phase 0 Resource UUID"),
        "status": fields.String(description="Current status (e.g., ACTIVE, DISABLED)"),
        "created_at": fields.DateTime(description="Creation timestamp"),
        "resource": fields.Nested(resource_nested_dto, skip_none=True),
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

vault_statistics_dto = vault_ns.model(
    "VaultStatistics",
    {
        "total_secrets": fields.Integer(description="Total number of secrets"),
        "active_secrets": fields.Integer(description="Number of active secrets"),
        "disabled_secrets": fields.Integer(description="Number of disabled secrets"),
        "recent_accesses": fields.Integer(description="Number of recent accesses"),
    },
)

vault_secret_response_wrapper = vault_ns.model(
    "VaultSecretResponseWrapper",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(secret_response_dto),
    },
)

vault_secret_list_wrapper = vault_ns.model(
    "VaultSecretListWrapper",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(secret_response_dto)),
    },
)

vault_stats_wrapper = vault_ns.model(
    "VaultStatsWrapper",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(vault_statistics_dto),
    },
)

vault_reveal_wrapper = vault_ns.model(
    "VaultRevealWrapper",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(secret_reveal_dto),
    },
)


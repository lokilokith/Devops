"""Schemas for Target Account Binding API."""

from __future__ import annotations

from marshmallow import Schema, fields


class TargetAccountBindingSchema(Schema):
    """Serialization schema for TargetAccountBinding."""

    id = fields.UUID(dump_only=True)
    control_plane_user_id = fields.UUID(required=True)
    resource_id = fields.UUID(required=True)
    target_os_username = fields.String(dump_only=True)
    ssh_credential_id = fields.UUID(dump_only=True, allow_none=True)
    status = fields.Function(
        lambda obj: (
            obj.status.value if hasattr(obj.status, "value") else str(obj.status)
        ),
        dump_only=True,
    )
    last_verified_at = fields.DateTime(dump_only=True, allow_none=True)
    failure_reason = fields.String(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class TargetAccountProvisionRequestSchema(Schema):
    """Input payload to trigger target account provisioning."""

    resource_id = fields.UUID(required=True)

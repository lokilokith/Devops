"""Vault Lifecycle API Schemas."""

from marshmallow import Schema, fields, validate
from app.vault_lifecycle.models import RotationStatus


class SecretRotationPolicyCreateSchema(Schema):
    vault_secret_id = fields.UUID(required=True)
    rotation_interval_seconds = fields.Int(required=True, validate=validate.Range(min=60))
    status = fields.Enum(RotationStatus, by_value=True, load_default=RotationStatus.ACTIVE)
    rotation_script_id = fields.UUID(allow_none=True)


class SecretRotationPolicyUpdateSchema(Schema):
    rotation_interval_seconds = fields.Int(validate=validate.Range(min=60))
    status = fields.Enum(RotationStatus, by_value=True)
    rotation_script_id = fields.UUID(allow_none=True)


class SecretRotationPolicyResponseSchema(Schema):
    id = fields.UUID()
    vault_secret_id = fields.UUID()
    rotation_interval_seconds = fields.Int()
    last_rotated_at = fields.DateTime(allow_none=True)
    next_rotation_at = fields.DateTime(allow_none=True)
    rotation_script_id = fields.UUID(allow_none=True)
    status = fields.Enum(RotationStatus, by_value=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class RotationEligibilityResponseSchema(Schema):
    status = fields.String()
    reason = fields.String()
    next_rotation_at = fields.DateTime(allow_none=True)

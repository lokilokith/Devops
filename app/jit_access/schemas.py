"""JIT Access API Schemas."""

from marshmallow import Schema, fields, validate

from app.jit_access.models import JITGrantStatus


class JITAccessRequestSchema(Schema):
    user_id = fields.UUID(required=True)
    role_id = fields.UUID(required=True)
    resource_id = fields.UUID(required=True)
    command_set_id = fields.String(required=False, load_default="system_health_check")
    duration_minutes = fields.Int(
        required=True, validate=validate.Range(min=1, max=480)
    )
    reason = fields.String(required=True, validate=validate.Length(min=3))
    context = fields.Dict(keys=fields.String(), required=False)


class JITAccessGrantResponseSchema(Schema):
    id = fields.UUID()
    user_id = fields.UUID()
    role_id = fields.UUID()
    resource_id = fields.UUID()
    target_account_binding_id = fields.UUID(allow_none=True)
    command_set_id = fields.String(allow_none=True)
    approved_by = fields.UUID(allow_none=True)
    approval_request_id = fields.UUID()
    status = fields.Enum(JITGrantStatus, by_value=True)
    created_at = fields.DateTime()
    activated_at = fields.DateTime(allow_none=True)
    expires_at = fields.DateTime(allow_none=True)
    revoked_at = fields.DateTime(allow_none=True)
    revocation_start = fields.DateTime(allow_none=True)
    revocation_complete = fields.DateTime(allow_none=True)
    observed_overrun_ms = fields.Int(allow_none=True)

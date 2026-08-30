"""JIT Access API Schemas."""

from marshmallow import Schema, fields, validate

from app.jit_access.models import JITGrantStatus


class JITAccessRequestSchema(Schema):
    user_id = fields.UUID(required=True)
    role_id = fields.UUID(required=True)
    resource_id = fields.UUID(required=True)
    duration_minutes = fields.Int(required=True, validate=validate.Range(min=1))
    reason = fields.String(required=True, validate=validate.Length(min=3))
    context = fields.Dict(keys=fields.String(), required=False)


class JITAccessGrantResponseSchema(Schema):
    id = fields.UUID()
    user_id = fields.UUID()
    role_id = fields.UUID()
    resource_id = fields.UUID()
    approved_by = fields.UUID(allow_none=True)
    approval_request_id = fields.UUID()
    status = fields.Enum(JITGrantStatus, by_value=True)
    created_at = fields.DateTime()
    activated_at = fields.DateTime(allow_none=True)
    expires_at = fields.DateTime(allow_none=True)
    revoked_at = fields.DateTime(allow_none=True)

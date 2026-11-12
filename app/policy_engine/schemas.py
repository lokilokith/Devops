"""Policy Engine REST API Schemas."""

from flask_restx import Namespace, fields

policies_ns = Namespace(
    "policy-engine", description="Policy Engine management and evaluation"
)

policy_base = {
    "name": fields.String(
        description="Policy Name", example="Restrict Production Access"
    ),
    "description": fields.String(
        description="Policy Description", example="Only allow during working hours"
    ),
    "conditions": fields.Raw(
        description="ABAC Conditions (JSON)",
        example={"allowed_hours": {"start": "09:00", "end": "18:00"}},
    ),
    "max_duration_seconds": fields.Integer(
        description="Max Session Duration", example=3600
    ),
    "requires_approval": fields.Boolean(description="Approval Required", example=True),
    "effect": fields.String(description="Effect (allow/deny)", example="allow"),
    "priority": fields.Integer(description="Evaluation Priority", example=10),
    "enabled": fields.Boolean(description="Is Policy Enabled", example=True),
}

policy_model = policies_ns.model(
    "AccessPolicy",
    {
        "id": fields.String(description="Policy UUID"),
        **policy_base,
        "created_at": fields.DateTime(),
        "updated_at": fields.DateTime(),
    },
)

policy_create_model = policies_ns.model(
    "PolicyCreate",
    {
        "name": fields.String(required=True, description="Policy Name"),
        "description": fields.String(description="Policy Description"),
        "conditions": fields.Raw(required=True, description="ABAC Conditions (JSON)"),
        "max_duration_seconds": fields.Integer(description="Max Session Duration"),
        "requires_approval": fields.Boolean(
            description="Approval Required", default=True
        ),
        "effect": fields.String(
            description="Effect", default="allow", enum=["allow", "deny"]
        ),
        "priority": fields.Integer(description="Priority", default=0),
        "enabled": fields.Boolean(description="Enabled", default=True),
    },
)

policy_update_model = policies_ns.model(
    "PolicyUpdate",
    {
        "description": fields.String(description="Policy Description"),
        "conditions": fields.Raw(description="ABAC Conditions (JSON)"),
        "max_duration_seconds": fields.Integer(description="Max Session Duration"),
        "requires_approval": fields.Boolean(description="Approval Required"),
        "priority": fields.Integer(description="Priority"),
        "enabled": fields.Boolean(description="Enabled"),
    },
)

policy_response_model = policies_ns.model(
    "PolicyResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(policy_model),
        "meta": fields.Raw,
    },
)

policy_list_response_model = policies_ns.model(
    "PolicyListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(policy_model)),
        "meta": fields.Raw,
    },
)

policy_evaluate_context_model = policies_ns.model(
    "PolicyEvaluateContext",
    {
        "ip": fields.String(description="Client IP Address", example="10.0.0.5"),
        "time": fields.String(
            description="ISO-8601 UTC Time", example="2023-01-01T12:00:00Z"
        ),
    },
)

policy_evaluate_request_model = policies_ns.model(
    "PolicyEvaluateRequest",
    {
        "user_id": fields.String(required=True, description="User UUID"),
        "resource_id": fields.String(
            required=True, description="Resource UUID or Code"
        ),
        "action": fields.String(required=True, description="Permission Action"),
        "context": fields.Nested(
            policy_evaluate_context_model, description="Evaluation Context"
        ),
    },
)

policy_evaluate_response_model = policies_ns.model(
    "PolicyEvaluateResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Raw(description="Evaluation Decision Details"),
        "meta": fields.Raw,
    },
)

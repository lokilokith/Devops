"""Vault Lifecycle Routes."""

from __future__ import annotations

import uuid
from flask import request, g
from flask_restx import Resource, Namespace, marshal
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from app.api.decorators import login_required
from app.api.responses import success_response
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.exceptions import AuthorizationDeniedError
from app.authorization.service import AuthorizationService
from app.extensions import db
from app.vault_lifecycle.exceptions import PolicyNotFoundError, PolicyValidationError
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.schemas import (
    SecretRotationPolicyCreateSchema,
    SecretRotationPolicyUpdateSchema,
    SecretRotationPolicyResponseSchema,
    RotationEligibilityResponseSchema
)
from app.vault_lifecycle.service import VaultLifecycleService


vault_lifecycle_ns = Namespace("vault-lifecycle", description="Vault Lifecycle Operations")

create_schema = SecretRotationPolicyCreateSchema()
update_schema = SecretRotationPolicyUpdateSchema()
response_schema = SecretRotationPolicyResponseSchema()


def get_lifecycle_service() -> VaultLifecycleService:
    return VaultLifecycleService(
        repository=SecretRotationPolicyRepository(db.session),
        audit_service=AuditService(AuditRepository(db.session)),
        authz_service=AuthorizationService(db.session),
        session=db.session
    )


@vault_lifecycle_ns.route("/policies")
class LifecyclePoliciesCollection(Resource):
    @login_required
    def post(self):
        """Create a new rotation policy."""
        try:
            data = create_schema.load(request.json)
        except Exception as e:
            raise BadRequest(str(e))
            
        service = get_lifecycle_service()
        try:
            policy = service.create_policy(uuid.UUID(g.user_id), data)
            data_resp = response_schema.dump(policy)
            return success_response(data=data_resp, status_code=201)
        except PolicyValidationError as e:
            raise BadRequest(str(e))
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))


@vault_lifecycle_ns.route("/policies/<uuid:policy_id>")
class LifecyclePolicyItem(Resource):
    @login_required
    def get(self, policy_id):
        """Get a rotation policy by ID."""
        service = get_lifecycle_service()
        try:
            policy = service.get_policy(uuid.UUID(g.user_id), policy_id)
            data_resp = response_schema.dump(policy)
            return success_response(data=data_resp, status_code=200)
        except PolicyNotFoundError as e:
            raise NotFound(str(e))
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))

    @login_required
    def put(self, policy_id):
        """Update a rotation policy."""
        try:
            data = update_schema.load(request.json)
        except Exception as e:
            raise BadRequest(str(e))
            
        service = get_lifecycle_service()
        try:
            policy = service.update_policy(uuid.UUID(g.user_id), policy_id, data)
            data_resp = response_schema.dump(policy)
            return success_response(data=data_resp, status_code=200)
        except PolicyNotFoundError as e:
            raise NotFound(str(e))
        except PolicyValidationError as e:
            raise BadRequest(str(e))
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))

    @login_required
    def delete(self, policy_id):
        """Delete a rotation policy."""
        service = get_lifecycle_service()
        try:
            service.delete_policy(uuid.UUID(g.user_id), policy_id)
            return success_response("Policy deleted", 200)
        except PolicyNotFoundError as e:
            raise NotFound(str(e))
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))


@vault_lifecycle_ns.route("/secrets/<uuid:secret_id>/evaluate")
class LifecyclePolicyEvaluate(Resource):
    @login_required
    def post(self, secret_id):
        """Evaluate a secret's rotation eligibility."""
        service = get_lifecycle_service()
        try:
            result = service.evaluate_secret(uuid.UUID(g.user_id), secret_id)
            return success_response(data=result, status_code=200)
        except AuthorizationDeniedError as e:
            raise Forbidden(str(e))

"""Target Account Binding API routes."""

from typing import cast
from uuid import UUID

from flask import g, request
from flask_restx import Namespace, Resource
from sqlalchemy.orm import Session
from werkzeug.exceptions import Forbidden, NotFound

from app.api.decorators import login_required
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.execution.executor import StubTargetExecutor
from app.identity.repository import IdentityRepository
from app.permissions.models import PermissionAction
from app.platform.extensions import db
from app.resources.repository import ResourcesRepository
from app.target_accounts.models import TargetAccountBinding
from app.target_accounts.repository import TargetAccountBindingRepository
from app.target_accounts.schemas import (
    TargetAccountBindingSchema,
    TargetAccountProvisionRequestSchema,
)
from app.target_accounts.service import TargetAccountService
from app.vault.crypto import EncryptionService, LocalKMSProvider

target_accounts_ns = Namespace(
    "target-accounts",
    description="Target Account Bindings & OS Identity Management",
)

binding_schema = TargetAccountBindingSchema()
bindings_schema = TargetAccountBindingSchema(many=True)
provision_request_schema = TargetAccountProvisionRequestSchema()


def _get_service() -> TargetAccountService:
    session = cast(Session, db.session)
    kms = LocalKMSProvider()
    enc = EncryptionService(kms)
    audit_svc = AuditService(AuditRepository(session))
    return TargetAccountService(
        session=session,
        binding_repo=TargetAccountBindingRepository(session),
        user_repo=IdentityRepository(session),
        resource_repo=ResourcesRepository(session),
        audit_service=audit_svc,
        executor=StubTargetExecutor(),
        encryption_service=enc,
    )


@target_accounts_ns.route("")
class TargetAccountBindingListResource(Resource):
    """List or create target account bindings."""

    @login_required
    def get(self):
        """List target account bindings for current user or all if admin."""
        current_user_id = UUID(g.user_id)
        session = cast(Session, db.session)
        authz = AuthorizationService(session)
        is_admin = authz.has_permission(
            current_user_id, "target_accounts", PermissionAction("read")
        )

        repo = TargetAccountBindingRepository(session)
        if is_admin:
            user_param = request.args.get("user_id")
            if user_param:
                bindings = repo.list_by_user(UUID(user_param))
            else:
                stmt = db.session.query(TargetAccountBinding)
                bindings = stmt.all()
        else:
            bindings = repo.list_by_user(current_user_id)

        return {
            "success": True,
            "data": bindings_schema.dump(bindings),
        }, 200

    @login_required
    def post(self):
        """Trigger target account provisioning for current user on a resource."""
        current_user_id = UUID(g.user_id)
        payload = request.get_json() or {}
        errors = provision_request_schema.validate(payload)
        if errors:
            return {"success": False, "errors": errors}, 400

        resource_id = UUID(payload["resource_id"])
        service = _get_service()

        try:
            binding = service.provision_target_account(
                user_id=current_user_id,
                resource_id=resource_id,
                triggered_by_user_id=current_user_id,
            )
            return {
                "success": True,
                "data": binding_schema.dump(binding),
            }, 201
        except ValueError as e:
            return {"success": False, "message": str(e)}, 400
        except RuntimeError as e:
            return {"success": False, "message": str(e)}, 500


@target_accounts_ns.route("/<string:binding_id>")
class TargetAccountBindingDetailResource(Resource):
    """View or delete a specific target account binding."""

    @login_required
    def get(self, binding_id: str):
        """Get details of a specific target account binding."""
        current_user_id = UUID(g.user_id)
        session = cast(Session, db.session)
        repo = TargetAccountBindingRepository(session)
        binding = repo.get_by_id(UUID(binding_id))
        if not binding:
            raise NotFound("Target account binding not found.")

        authz = AuthorizationService(session)
        is_admin = authz.has_permission(
            current_user_id, "target_accounts", PermissionAction("read")
        )

        if not is_admin and binding.control_plane_user_id != current_user_id:
            raise Forbidden(
                "You do not have permission to view this target account binding."
            )

        return {
            "success": True,
            "data": binding_schema.dump(binding),
        }, 200

    @login_required
    def delete(self, binding_id: str):
        """Remove a target account binding."""
        current_user_id = UUID(g.user_id)
        session = cast(Session, db.session)
        repo = TargetAccountBindingRepository(session)
        binding = repo.get_by_id(UUID(binding_id))
        if not binding:
            raise NotFound("Target account binding not found.")

        authz = AuthorizationService(session)
        is_admin = authz.has_permission(
            current_user_id, "target_accounts", PermissionAction("delete")
        )

        if not is_admin and binding.control_plane_user_id != current_user_id:
            raise Forbidden(
                "You do not have permission to delete this target account binding."
            )

        service = _get_service()
        try:
            removed_binding = service.remove_target_account(
                binding_id=binding.id,
                actor_user_id=current_user_id,
            )
            return {
                "success": True,
                "data": binding_schema.dump(removed_binding),
            }, 200
        except Exception as e:
            return {"success": False, "message": str(e)}, 500

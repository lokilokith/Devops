"""JIT Access API Routes."""

from uuid import UUID

from flask import g, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from app.access_requests.repository import AccessRequestRepository
from app.access_requests.service import AccessRequestService
from app.api.decorators import login_required, requires_permission
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.jit_access.exceptions import GrantNotFoundError
from app.jit_access.repository import JITAccessRepository
from app.jit_access.schemas import JITAccessGrantResponseSchema, JITAccessRequestSchema
from app.jit_access.service import JITAccessService
from app.permissions.models import PermissionAction
from app.platform.extensions import db
from app.policy_engine.repository import PolicyRepository
from app.policy_engine.service import PolicyService
from app.shared.exceptions import ValidationException

jit_ns = Namespace("jit", description="JIT Privileged Access operations")


def build_jit_service() -> JITAccessService:
    from app.identity.repository import IdentityRepository
    from app.resources.repository import ResourcesRepository
    from app.roles.repository import RolesRepository
    from app.user_roles.repository import UserRolesRepository

    ar_repo = AccessRequestRepository(db.session)
    user_repo = IdentityRepository(db.session)
    role_repo = RolesRepository(db.session)
    res_repo = ResourcesRepository(db.session)
    ur_repo = UserRolesRepository(db.session)

    ar_service = AccessRequestService(ar_repo, user_repo, role_repo, res_repo, ur_repo)

    auth_service = AuthorizationService(db.session)
    audit_service = AuditService(AuditRepository(db.session))

    policy_service = PolicyService(
        PolicyRepository(db.session), auth_service, audit_service
    )

    return JITAccessService(
        JITAccessRepository(), ar_service, policy_service, audit_service, auth_service
    )


@jit_ns.route("/request")
class JITRequestResource(Resource):
    @login_required
    @requires_permission("jit_grants", "create")
    def post(self):
        """Request JIT privileged access."""
        schema = JITAccessRequestSchema()
        try:
            data = schema.load(request.get_json())
        except ValidationError as e:
            raise ValidationException(str(e.messages))

        svc = build_jit_service()

        if str(data["user_id"]) != g.user_id:
            try:
                is_admin = svc._auth.has_permission(
                    UUID(g.user_id), "jit_grants", PermissionAction.UPDATE
                )
                if not is_admin:
                    raise ValidationException(
                        "Cannot request access for another user without admin privileges"
                    )
            except ValueError:
                raise ValidationException(
                    "Cannot request access for another user without admin privileges"
                )

        grant = svc.request_access(
            requester_id=data["user_id"],
            role_id=data["role_id"],
            resource_id=data["resource_id"],
            duration_minutes=data["duration_minutes"],
            reason=data["reason"],
            command_set_id=data.get("command_set_id", "system_health_check"),
            context=data.get("context", {}),
        )
        return JITAccessGrantResponseSchema().dump(grant), 201


@jit_ns.route("/grants")
class JITGrantsResource(Resource):
    @login_required
    @requires_permission("jit_grants", "read")
    def get(self):
        """List JIT grants."""
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        status = request.args.get("status")
        user_id_str = request.args.get("user_id")

        user_id = UUID(user_id_str) if user_id_str else None

        from app.jit_access.models import JITGrantStatus

        status_enum = JITGrantStatus(status) if status else None

        grants, total = JITAccessRepository.list_grants(
            user_id=user_id, status=status_enum, limit=limit, offset=offset
        )

        return {
            "items": JITAccessGrantResponseSchema(many=True).dump(grants),
            "total": total,
            "limit": limit,
            "offset": offset,
        }, 200


@jit_ns.route("/<uuid:grant_id>")
class JITDetailResource(Resource):
    @login_required
    @requires_permission("jit_grants", "read")
    def get(self, grant_id: UUID):
        """Get details of a JIT grant."""
        svc = build_jit_service()
        try:
            grant = svc.get_grant(grant_id)
        except GrantNotFoundError:
            return {"message": f"Grant {grant_id} not found"}, 404
        return JITAccessGrantResponseSchema().dump(grant), 200


@jit_ns.route("/<uuid:grant_id>/activate")
class JITActivateResource(Resource):
    @login_required
    def post(self, grant_id: UUID):
        """Activate a pending JIT grant."""
        svc = build_jit_service()
        grant = svc.activate_grant(grant_id, UUID(g.user_id))
        return JITAccessGrantResponseSchema().dump(grant), 200


@jit_ns.route("/<uuid:grant_id>/revoke")
class JITRevokeResource(Resource):
    @login_required
    def post(self, grant_id: UUID):
        """Revoke a JIT grant."""
        svc = build_jit_service()
        grant = svc.revoke_access(grant_id, UUID(g.user_id))
        return JITAccessGrantResponseSchema().dump(grant), 200


@jit_ns.route("/<uuid:grant_id>/sessions")
class JITRegisterSessionResource(Resource):
    @login_required
    def post(self, grant_id: UUID):
        """Register an active JIT session with PID identity."""
        data = request.get_json() or {}
        session_id_str = data.get("session_id")
        pid = data.get("target_session_pid") or data.get("pid")

        if not session_id_str or not pid:
            raise ValidationException("Missing session_id or target_session_pid")

        try:
            session_id = UUID(str(session_id_str))
            pid_int = int(pid)
        except (ValueError, TypeError) as e:
            raise ValidationException(f"Invalid session parameters: {e}")

        svc = build_jit_service()
        session_rec = svc.register_active_session(
            grant_id=grant_id,
            user_id=UUID(g.user_id),
            session_id=session_id,
            target_session_pid=pid_int,
        )
        return {
            "session_id": str(session_rec.id),
            "grant_id": str(grant_id),
            "status": session_rec.status,
        }, 201


@jit_ns.route("/<uuid:grant_id>/terminate-sessions")
class JITTerminateSessionsResource(Resource):
    @login_required
    def post(self, grant_id: UUID):
        """Terminate active sessions associated with a JIT grant."""
        svc = build_jit_service()
        count = svc.terminate_active_sessions(grant_id, UUID(g.user_id))
        return {
            "grant_id": str(grant_id),
            "terminated_count": count,
        }, 200


@jit_ns.route("/session/current")
class JITCurrentSessionResource(Resource):
    @login_required
    def get(self):
        """Get active JIT sessions for the current user."""
        from app.jit_access.models import JITGrantStatus

        grants, _ = JITAccessRepository.list_grants(
            user_id=UUID(g.user_id), status=JITGrantStatus.ACTIVE, limit=100
        )
        return JITAccessGrantResponseSchema(many=True).dump(grants), 200

import logging
from uuid import UUID

from flask import g
from flask_restx import Namespace, Resource
from werkzeug.exceptions import Forbidden, NotFound

from app.api.decorators import login_required, requires_permission
from app.authorization.service import AuthorizationService
from app.notifications.schemas import (
    notification_list_parser,
    notification_list_response_model,
    notification_mark_all_response_model,
    notification_response_model,
    notification_single_response_model,
    notification_unread_count_model,
    unread_count_data_model,
)
from app.notifications.validators import validate_filter_params
from app.permissions.models import PermissionAction
from app.platform.extensions import db

logger = logging.getLogger(__name__)

notifications_ns = Namespace(
    "notifications", description="Notification Engine Operations"
)

# Add models to namespace
notifications_ns.models[notification_response_model.name] = notification_response_model
notifications_ns.models[notification_list_response_model.name] = (
    notification_list_response_model
)
notifications_ns.models[notification_single_response_model.name] = (
    notification_single_response_model
)
notifications_ns.models[notification_unread_count_model.name] = (
    notification_unread_count_model
)
notifications_ns.models[notification_mark_all_response_model.name] = (
    notification_mark_all_response_model
)
notifications_ns.models[unread_count_data_model.name] = unread_count_data_model


def get_service():
    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.notifications.providers.console import ConsoleEmailProvider
    from app.notifications.repository import NotificationRepository
    from app.notifications.service import NotificationService

    return NotificationService(
        repository=NotificationRepository(db.session),
        audit_service=AuditService(AuditRepository(db.session)),
        provider=ConsoleEmailProvider(),
        session=db.session,
    )


@notifications_ns.route("")
class NotificationListResource(Resource):
    @login_required
    @notifications_ns.expect(notification_list_parser)
    @notifications_ns.marshal_with(notification_list_response_model)
    def get(self):
        """List notifications."""
        args = notification_list_parser.parse_args()
        parsed_filters = validate_filter_params(args)

        user_id = UUID(g.user_id)

        # Enforce Ownership/Admin read access
        authz = AuthorizationService(db.session)
        is_admin = authz.has_permission(user_id, "notifications", PermissionAction.READ)

        if "recipient_id" in parsed_filters:
            requested_recipient = parsed_filters["recipient_id"]
            if str(requested_recipient) != str(user_id) and not is_admin:
                raise Forbidden("Cannot read notifications of another user.")
        else:
            if not is_admin:
                parsed_filters["recipient_id"] = user_id

        svc = get_service()
        notifs = svc.list_notifications(**parsed_filters)
        return {"success": True, "data": notifs}


@notifications_ns.route("/unread-count")
class NotificationUnreadCountResource(Resource):
    @login_required
    @notifications_ns.marshal_with(notification_unread_count_model)
    def get(self):
        """Get unread notification count for current user."""
        svc = get_service()
        count = svc.count_unread(UUID(g.user_id))
        return {"success": True, "data": {"unread_count": count}}


@notifications_ns.route("/read-all")
class NotificationReadAllResource(Resource):
    @login_required
    @notifications_ns.marshal_with(notification_mark_all_response_model)
    def patch(self):
        """Mark all notifications as read for current user."""
        svc = get_service()
        count = svc.mark_all_as_read(UUID(g.user_id))
        return {"success": True, "data": count}


@notifications_ns.route("/<uuid:notification_id>")
class NotificationResource(Resource):
    @login_required
    @notifications_ns.marshal_with(notification_single_response_model)
    def get(self, notification_id):
        """Get a notification by ID."""
        svc = get_service()
        # Not best, let's use a get_by_id from repo directly, wait service doesn't
        # have get_by_id!
        svc.list_notifications()
        # Instead I'll use list_notifications with limit=1, or just fetch via repo.
        notif = svc._repo.get_by_id(notification_id)
        if not notif:
            raise NotFound("Notification not found.")

        user_id = UUID(g.user_id)
        authz = AuthorizationService(db.session)
        is_admin = authz.has_permission(user_id, "notifications", PermissionAction.READ)

        if str(notif.recipient_user_id) != str(user_id) and not is_admin:
            raise Forbidden("Cannot read this notification.")

        return {"success": True, "data": notif}

    @login_required
    @requires_permission("notifications", PermissionAction.DELETE)
    def delete(self, notification_id):
        """Delete a notification (Admin only, as per typical REST, but let's allow owners too via service)."""
        svc = get_service()
        notif = svc._repo.get_by_id(notification_id)
        if not notif:
            raise NotFound("Notification not found.")

        user_id = UUID(g.user_id)
        authz = AuthorizationService(db.session)
        is_admin = authz.has_permission(
            user_id, "notifications", PermissionAction.DELETE
        )

        if str(notif.recipient_user_id) != str(user_id) and not is_admin:
            raise Forbidden("Cannot delete this notification.")

        svc.delete_notification(notification_id, user_id)
        return "", 204


@notifications_ns.route("/<uuid:notification_id>/read")
class NotificationReadResource(Resource):
    @login_required
    @notifications_ns.marshal_with(notification_single_response_model)
    def patch(self, notification_id):
        """Mark a notification as read."""
        svc = get_service()
        try:
            notif = svc.mark_as_read(notification_id, UUID(g.user_id))
            return {"success": True, "data": notif}
        except Exception as e:
            if "not found" in str(e).lower():
                raise NotFound("Notification not found.")
            if "not authorized" in str(e).lower():
                raise Forbidden(str(e))
            raise

import logging
from flask import Flask
from app.notifications.events import (
    access_request_created,
    request_approved,
    request_rejected,
    request_cancelled,
    approval_required,
    workflow_failed,
    role_provisioned,
    audit_alert,
)
from app.notifications.models import NotificationType, NotificationPriority

logger = logging.getLogger(__name__)


def register_notification_handlers(app: Flask) -> None:
    """Register blinker signal handlers for the notification engine."""

    def handle_event(sender, **kwargs):
        # We need the app context to use the db and services.
        # Since signals are emitted during a request, we are already in app context.
        # However, it's safer to just fetch the service inside.
        payload = kwargs.get("payload", {})
        event_name = payload.get("event")
        recipient_id = payload.get("recipient_id")
        if not recipient_id:
            logger.warning(
                f"Notification skipped for event '{event_name}': No recipient_id provided."
            )
            return

        title = payload.get("title", f"New {event_name.replace('_', ' ').title()}")
        message = payload.get(
            "message", f"You have a new notification regarding {event_name}."
        )
        type_str = payload.get("type")
        priority_str = payload.get("priority", "normal")
        metadata = payload.get("metadata", {})

        try:
            type_enum = NotificationType(type_str)
        except ValueError:
            type_enum = NotificationType.SYSTEM

        try:
            priority_enum = NotificationPriority(priority_str)
        except ValueError:
            priority_enum = NotificationPriority.NORMAL

        from app.notifications.service import NotificationService
        from app.notifications.repository import NotificationRepository
        from app.notifications.providers.console import ConsoleEmailProvider
        from app.audit.service import AuditService
        from app.audit.repository import AuditRepository
        from app.platform.extensions import db

        service = NotificationService(
            repository=NotificationRepository(db.session),
            audit_service=AuditService(AuditRepository(db.session)),
            provider=ConsoleEmailProvider(),
            session=db.session,
        )

        try:
            service.create_notification(
                recipient_user_id=recipient_id,
                title=title,
                message=message,
                type_=type_enum,
                priority=priority_enum,
                metadata_payload=metadata,
            )
        except Exception as e:
            logger.error(f"Failed to create notification for event {event_name}: {e}")

    # Register handlers for all signals
    access_request_created.connect(handle_event, weak=False)
    request_approved.connect(handle_event, weak=False)
    request_rejected.connect(handle_event, weak=False)
    request_cancelled.connect(handle_event, weak=False)
    approval_required.connect(handle_event, weak=False)
    workflow_failed.connect(handle_event, weak=False)
    role_provisioned.connect(handle_event, weak=False)
    audit_alert.connect(handle_event, weak=False)

    logger.info("Notification handlers registered.")

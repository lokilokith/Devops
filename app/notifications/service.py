from typing import Sequence, Any, Dict
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.notifications.models import (
    Notification,
    NotificationStatus,
    NotificationType,
    NotificationPriority,
)
from app.notifications.repository import (
    NotificationRepository,
    NotificationNotFoundError,
)
from app.notifications.providers.base import NotificationProvider
from app.audit.service import AuditService
from app.audit.models import AuditStatus, AuditSeverity


class NotificationValidationError(Exception):
    pass


class NotificationServiceError(Exception):
    pass


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        audit_service: AuditService,
        provider: NotificationProvider,
        session: Session,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._provider = provider
        self._session = session

    def create_notification(
        self,
        recipient_user_id: UUID,
        title: str,
        message: str,
        type_: NotificationType,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata_payload: Dict[str, Any] | None = None,
    ) -> Notification:
        if not title or len(title) > 255:
            raise NotificationValidationError(
                "Title must be between 1 and 255 characters."
            )
        if not message:
            raise NotificationValidationError("Message cannot be empty.")

        try:
            notification = Notification(
                recipient_user_id=str(recipient_user_id),
                title=title,
                message=message,
                type=type_,
                priority=priority,
                metadata_payload=metadata_payload or {},
            )
            created = self._repo.create_notification(notification)
            self._session.commit()

            self._audit.log_event(
                action="notification.created",
                resource_type="notifications",
                resource_id=str(created.id),
                actor_user_id=recipient_user_id,
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={"type": type_.value, "priority": priority.value},
            )

            # Attempt delivery synchronously for now, or could be async later
            return self.send_email(created.id)

        except Exception as err:
            self._session.rollback()
            raise NotificationServiceError(
                f"Failed to create notification: {str(err)}"
            ) from err

    def send_email(self, notification_id: UUID) -> Notification:
        try:
            notif = self._repo.get_by_id(notification_id)
            if not notif:
                raise NotificationNotFoundError("Notification not found.")

            notif.delivery_attempts += 1

            try:
                success = self._provider.send(notif)
                if success:
                    notif.status = NotificationStatus.SENT
                    notif.last_error = None
                    self._repo.update_notification(notif)
                    self._session.commit()

                    self._audit.log_event(
                        action="notification.sent",
                        resource_type="notifications",
                        resource_id=str(notif.id),
                        actor_user_id=notif.recipient_user_id,
                        status=AuditStatus.SUCCESS,
                        severity=AuditSeverity.INFO,
                    )
                else:
                    raise Exception("Provider returned False.")

            except Exception as e:
                notif.status = NotificationStatus.FAILED
                notif.last_error = str(e)
                self._repo.update_notification(notif)
                self._session.commit()

                self._audit.log_event(
                    action="notification.failed",
                    resource_type="notifications",
                    resource_id=str(notif.id),
                    actor_user_id=notif.recipient_user_id,
                    status=AuditStatus.FAILED,
                    severity=AuditSeverity.HIGH,
                    details={"error": str(e), "attempts": notif.delivery_attempts},
                )

            return notif
        except Exception as err:
            self._session.rollback()
            raise NotificationServiceError(f"Failed to send email: {str(err)}") from err

    def mark_as_read(self, notification_id: UUID, user_id: UUID) -> Notification:
        try:
            notif = self._repo.get_by_id(notification_id)
            if not notif:
                raise NotificationNotFoundError("Notification not found.")

            if str(notif.recipient_user_id) != str(user_id):
                raise NotificationValidationError(
                    "Not authorized to mark this notification as read."
                )

            if not notif.is_read:
                notif.is_read = True
                notif.read_at = datetime.utcnow()
                notif.status = NotificationStatus.READ
                self._repo.update_notification(notif)
                self._session.commit()

                self._audit.log_event(
                    action="notification.read",
                    resource_type="notifications",
                    resource_id=str(notif.id),
                    actor_user_id=user_id,
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                )

            return notif
        except Exception as err:
            self._session.rollback()
            raise NotificationServiceError(
                f"Failed to mark notification as read: {str(err)}"
            ) from err

    def mark_all_as_read(self, user_id: UUID) -> int:
        try:
            count = self._repo.mark_all_as_read(user_id)
            self._session.commit()
            if count > 0:
                self._audit.log_event(
                    action="notification.read_all",
                    resource_type="notifications",
                    resource_id="multiple",
                    actor_user_id=user_id,
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={"count": count},
                )
            return count
        except Exception as err:
            self._session.rollback()
            raise NotificationServiceError(
                f"Failed to mark all as read: {str(err)}"
            ) from err

    def list_notifications(
        self,
        recipient_id: UUID | None = None,
        status: NotificationStatus | None = None,
        type_: NotificationType | None = None,
        priority: NotificationPriority | None = None,
        is_read: bool | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Notification]:
        return self._repo.list_notifications(
            recipient_id,
            status,
            type_,
            priority,
            is_read,
            created_after,
            created_before,
            limit,
            offset,
        )

    def count_unread(self, user_id: UUID) -> int:
        return self._repo.count_unread(user_id)

    def delete_notification(self, notification_id: UUID, user_id: UUID) -> None:
        try:
            notif = self._repo.get_by_id(notification_id)
            if not notif:
                raise NotificationNotFoundError("Notification not found.")

            # Ownership will be handled by the route, but double check here or trust the caller.
            self._repo.delete_notification(notification_id)
            self._session.commit()

            self._audit.log_event(
                action="notification.deleted",
                resource_type="notifications",
                resource_id=str(notification_id),
                actor_user_id=user_id,
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
            )
        except Exception as err:
            self._session.rollback()
            raise NotificationServiceError(
                f"Failed to delete notification: {str(err)}"
            ) from err

    def retry_failed_notifications(self, max_attempts: int = 3) -> int:
        try:
            failed = self._repo.get_failed_notifications(max_attempts)
            success_count = 0
            for notif in failed:
                # send_email internally increments attempts, sets status and commits.
                # To avoid nested partial transactions, we just call it.
                updated_notif = self.send_email(notif.id)
                if updated_notif.status == NotificationStatus.SENT:
                    success_count += 1
            return success_count
        except Exception as err:
            raise NotificationServiceError(
                f"Failed to retry notifications: {str(err)}"
            ) from err

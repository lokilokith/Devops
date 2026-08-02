from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


class NotificationRepositoryError(Exception):
    pass


class NotificationNotFoundError(Exception):
    pass


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_notification(self, notification: Notification) -> Notification:
        try:
            self._session.add(notification)
            self._session.flush()
            return notification
        except SQLAlchemyError as err:
            self._session.rollback()
            raise NotificationRepositoryError("Failed to create notification.") from err

    def get_by_id(self, notification_id: UUID) -> Notification | None:
        try:
            return (
                self._session.query(Notification).filter_by(id=notification_id).first()
            )
        except SQLAlchemyError as err:
            raise NotificationRepositoryError("Failed to fetch notification.") from err

    def update_notification(self, notification: Notification) -> Notification:
        try:
            self._session.flush()
            return notification
        except SQLAlchemyError as err:
            self._session.rollback()
            raise NotificationRepositoryError("Failed to update notification.") from err

    def delete_notification(self, notification_id: UUID) -> None:
        try:
            notif = self.get_by_id(notification_id)
            if not notif:
                raise NotificationNotFoundError("Notification not found.")
            self._session.delete(notif)
            self._session.flush()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise NotificationRepositoryError("Failed to delete notification.") from err

    def count_unread(self, user_id: UUID) -> int:
        try:
            return (
                self._session.query(Notification)
                .filter_by(recipient_user_id=user_id, is_read=False)
                .count()
            )
        except SQLAlchemyError as err:
            raise NotificationRepositoryError(
                "Failed to count unread notifications."
            ) from err

    def mark_all_as_read(self, user_id: UUID) -> int:
        try:
            notifs = (
                self._session.query(Notification)
                .filter_by(recipient_user_id=user_id, is_read=False)
                .all()
            )
            count = len(notifs)
            for notif in notifs:
                notif.is_read = True
                notif.read_at = datetime.utcnow()
                notif.status = NotificationStatus.READ
            self._session.flush()
            return count
        except SQLAlchemyError as err:
            self._session.rollback()
            raise NotificationRepositoryError(
                "Failed to mark notifications as read."
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
        try:
            query = self._session.query(Notification)

            if recipient_id:
                query = query.filter(
                    Notification.recipient_user_id == recipient_id
                )
            if status:
                query = query.filter(Notification.status == status)
            if type_:
                query = query.filter(Notification.type == type_)
            if priority:
                query = query.filter(Notification.priority == priority)
            if is_read is not None:
                query = query.filter(Notification.is_read == is_read)
            if created_after:
                query = query.filter(Notification.created_at >= created_after)
            if created_before:
                query = query.filter(Notification.created_at <= created_before)

            return (
                query.order_by(desc(Notification.created_at))
                .offset(offset)
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as err:
            raise NotificationRepositoryError("Failed to list notifications.") from err

    def get_failed_notifications(self, max_attempts: int = 3) -> Sequence[Notification]:
        try:
            return (
                self._session.query(Notification)
                .filter(
                    Notification.status == NotificationStatus.FAILED,
                    Notification.delivery_attempts < max_attempts,
                )
                .all()
            )
        except SQLAlchemyError as err:
            raise NotificationRepositoryError(
                "Failed to fetch failed notifications."
            ) from err

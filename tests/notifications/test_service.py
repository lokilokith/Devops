import uuid
from unittest.mock import Mock

import pytest

from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.notifications.models import (
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.notifications.providers.base import NotificationProvider
from app.notifications.repository import NotificationRepository
from app.notifications.service import NotificationService, NotificationValidationError


class DummyProvider(NotificationProvider):
    def __init__(self, succeed=True):
        self.succeed = succeed
        self.sent_notifications = []

    def send(self, notification):
        if self.succeed:
            self.sent_notifications.append(notification)
            return True
        raise Exception("Provider failed")


def test_create_notification_success(app, db_session):
    repo = NotificationRepository(db_session)
    audit = AuditService(AuditRepository(db_session))
    provider = DummyProvider(succeed=True)

    svc = NotificationService(repo, audit, provider, db_session)
    user_id = uuid.uuid4()

    n = svc.create_notification(
        recipient_user_id=user_id,
        title="Welcome",
        message="Hello World",
        type_=NotificationType.SYSTEM,
    )

    assert n.title == "Welcome"
    assert n.status == NotificationStatus.SENT
    assert n.delivery_attempts == 1
    assert len(provider.sent_notifications) == 1


def test_create_notification_provider_failure(app, db_session):
    repo = NotificationRepository(db_session)
    audit = AuditService(AuditRepository(db_session))
    provider = DummyProvider(succeed=False)

    svc = NotificationService(repo, audit, provider, db_session)
    user_id = uuid.uuid4()

    n = svc.create_notification(
        recipient_user_id=user_id,
        title="Fail Test",
        message="Will fail",
        type_=NotificationType.SYSTEM,
    )

    # Should not raise, but status should be FAILED
    assert n.status == NotificationStatus.FAILED
    assert n.delivery_attempts == 1
    assert "Provider failed" in n.last_error


def test_retry_failed_notifications(app, db_session):
    repo = NotificationRepository(db_session)
    audit = AuditService(AuditRepository(db_session))
    provider = DummyProvider(succeed=False)

    svc = NotificationService(repo, audit, provider, db_session)
    user_id = uuid.uuid4()

    n = svc.create_notification(
        recipient_user_id=user_id,
        title="Fail Test",
        message="Will fail",
        type_=NotificationType.SYSTEM,
    )

    assert n.status == NotificationStatus.FAILED

    # Fix the provider
    svc._provider = DummyProvider(succeed=True)
    success_count = svc.retry_failed_notifications()

    assert success_count == 1

    updated = repo.get_by_id(n.id)
    assert updated.status == NotificationStatus.SENT
    assert updated.delivery_attempts == 2


def test_mark_as_read(app, db_session):
    repo = NotificationRepository(db_session)
    audit = AuditService(AuditRepository(db_session))
    provider = DummyProvider(succeed=True)

    svc = NotificationService(repo, audit, provider, db_session)
    user_id = uuid.uuid4()

    n = svc.create_notification(
        recipient_user_id=user_id,
        title="Unread",
        message="Read me",
        type_=NotificationType.SYSTEM,
    )

    assert n.is_read is False

    read_n = svc.mark_as_read(n.id, user_id)
    assert read_n.is_read is True
    assert read_n.status == NotificationStatus.READ

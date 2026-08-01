import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.notifications.repository import (
    NotificationNotFoundError,
    NotificationRepository,
)


def test_create_notification(app, db_session: Session):
    repo = NotificationRepository(db_session)
    user_id = str(uuid.uuid4())

    n = Notification(
        recipient_user_id=user_id,
        title="Test Notification",
        message="This is a test",
        type=NotificationType.SYSTEM,
        priority=NotificationPriority.NORMAL,
    )

    created = repo.create_notification(n)
    db_session.commit()

    assert created.id is not None
    assert created.title == "Test Notification"
    assert created.status == NotificationStatus.PENDING


def test_get_by_id(app, db_session: Session):
    repo = NotificationRepository(db_session)
    user_id = str(uuid.uuid4())

    n = Notification(
        recipient_user_id=user_id,
        title="Test Notification",
        message="This is a test",
        type=NotificationType.SYSTEM,
    )
    created = repo.create_notification(n)
    db_session.commit()

    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id


def test_count_unread_and_mark_read(app, db_session: Session):
    repo = NotificationRepository(db_session)
    user_id = str(uuid.uuid4())

    for i in range(3):
        repo.create_notification(
            Notification(
                recipient_user_id=user_id,
                title=f"Test {i}",
                message="Message",
                type=NotificationType.SYSTEM,
            )
        )
    db_session.commit()

    assert repo.count_unread(uuid.UUID(user_id)) == 3

    count = repo.mark_all_as_read(uuid.UUID(user_id))
    db_session.commit()
    assert count == 3

    assert repo.count_unread(uuid.UUID(user_id)) == 0

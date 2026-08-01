import pytest
import uuid
from app.platform.extensions import db
from app.notifications.models import Notification, NotificationType, NotificationStatus
from app.identity.models import User, UserStatus
from tests.api.test_decorators import create_mock_token


def setup_admin_user(db_session, app):
    u = User(
        employee_id="NOTIF_ADM",
        username="notif_admin",
        email="notif@test.com",
        full_name="Admin",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    token = create_mock_token(app, u.id)
    return token, u.id


def test_get_notifications(client, db_session, app):
    token, admin_id = setup_admin_user(db_session, app)
    # Setup some notifications
    n1 = Notification(
        recipient_user_id=str(admin_id),
        title="Admin Alert",
        message="System alert",
        type=NotificationType.SYSTEM,
        status=NotificationStatus.SENT,
    )
    db_session.add(n1)
    db_session.commit()

    resp = client.get("/notifications", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json["data"]
    assert len(data) >= 1
    assert data[0]["title"] == "Admin Alert"


def test_unread_count(client, db_session, app):
    token, admin_id = setup_admin_user(db_session, app)

    n1 = Notification(
        recipient_user_id=str(admin_id),
        title="Unread Alert",
        message="System alert",
        type=NotificationType.SYSTEM,
        status=NotificationStatus.SENT,
    )
    db_session.add(n1)
    db_session.commit()

    resp = client.get(
        "/notifications/unread-count", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert "data" in resp.json
    assert resp.json["data"]["unread_count"] >= 1


def test_read_all(client, db_session, app):
    token, admin_id = setup_admin_user(db_session, app)
    resp = client.patch(
        "/notifications/read-all", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert "data" in resp.json

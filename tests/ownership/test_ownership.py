def test_owner_can_read_notification_returns_200(
    client, normal_token, normal_user, db_session
):
    from tests.fixtures.factories import NotificationFactory

    notif = NotificationFactory(recipient=normal_user)
    db_session.add(notif)
    db_session.flush()

    resp = client.get(
        f"/notifications/{notif.id}",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 200


def test_non_owner_cannot_read_notification_returns_403(
    client, normal_token, admin_user, db_session
):
    from tests.fixtures.factories import NotificationFactory

    # Notif belongs to admin
    notif = NotificationFactory(recipient=admin_user)
    db_session.add(notif)
    db_session.flush()

    resp = client.get(
        f"/notifications/{notif.id}",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 403


def test_owner_can_read_access_request_returns_200(
    client, normal_token, normal_user, db_session
):
    from tests.fixtures.factories import AccessRequestFactory

    req = AccessRequestFactory(requester=normal_user)
    db_session.add(req)
    db_session.flush()

    resp = client.get(
        f"/access-requests/{req.id}",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 200


def test_non_owner_cannot_read_access_request_returns_404(
    client, normal_token, admin_user, db_session
):
    from tests.fixtures.factories import AccessRequestFactory

    req = AccessRequestFactory(requester=admin_user)
    db_session.add(req)
    db_session.flush()

    resp = client.get(
        f"/access-requests/{req.id}",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    # Masks as 404 to prevent enumeration
    assert resp.status_code == 404

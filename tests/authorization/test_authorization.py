def test_admin_can_access_protected_route_returns_200(client, admin_token):
    resp = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


def test_normal_user_cannot_access_protected_route_returns_403(client, normal_token):
    resp = client.get("/users", headers={"Authorization": f"Bearer {normal_token}"})
    assert resp.status_code == 403


def test_sec_admin_can_access_protected_route_returns_200(client, sec_admin_token):
    # This proves the BFLA vulnerability is fixed and the role is no longer orphaned.
    resp = client.get("/users", headers={"Authorization": f"Bearer {sec_admin_token}"})
    assert resp.status_code == 200

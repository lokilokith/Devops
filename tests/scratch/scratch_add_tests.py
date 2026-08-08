with open('tests/identity/test_routes.py', 'a') as f:
    f.write('''

def test_disable_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.deactivate_user.return_value = {"id": uid}
    res = client.post(f"/users/{uid}/disable", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200

def test_enable_user(client, mock_auth, mock_service):
    uid = str(uuid4())
    mock_service.activate_user.return_value = {"id": uid}
    res = client.post(f"/users/{uid}/enable", headers={"Authorization": "Bearer token"})
    assert res.status_code == 200
''')

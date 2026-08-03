import pytest
from app.identity.models import User, UserStatus
from app.access_requests.models import AccessRequest, RequestStatus
from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus

def test_frontend_user_creation_payload(client, admin_token):
    # Simulates the payload sent from the frontend when fields like title are omitted
    res = client.post(
        "/users",
        json={
            "employee_id": "EMP_FRONTEND",
            "username": "frontend_user",
            "email": "frontend@example.com",
            "full_name": "Frontend User",
            "password": "password123",
            "title": "" # Frontend might send empty string
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 201
    assert res.json["data"]["username"] == "frontend_user"

def test_user_create_refresh(client, admin_token, db_session):
    # Just verifies that creating a user makes them visible in lists immediately
    client.post(
        "/users",
        json={
            "employee_id": "EMP_REFRESH",
            "username": "refresh_user",
            "email": "refresh@example.com",
            "full_name": "Refresh User",
            "password": "password123"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    res = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    usernames = [u["username"] for u in res.json["data"]]
    assert "refresh_user" in usernames

def test_access_request_creates_workflow(client, user_token, db_session, test_role):
    from uuid import UUID
    res = client.post(
        "/access-requests",
        json={
            "requested_role_id": test_role.id,
            "business_justification": "Need access to test role"
        },
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert res.status_code == 201
    req_id = res.json["data"]["id"]
    
    # Check if workflow was created
    workflow = db_session.query(ApprovalWorkflow).filter_by(access_request_id=UUID(req_id)).first()
    assert workflow is not None

def test_pending_request_visible_in_approval_queue(client, admin_token, user_token, test_role):
    res = client.post(
        "/access-requests",
        json={
            "requested_role_id": test_role.id,
            "business_justification": "Need access for approval queue test"
        },
        headers={"Authorization": f"Bearer {user_token}"}
    )
    req_id = res.json["data"]["id"]
    
    # Admin checks approval queue
    queue_res = client.get("/approval-workflows", headers={"Authorization": f"Bearer {admin_token}"})
    assert queue_res.status_code == 200
    requests = [w["access_request_id"] for w in queue_res.json["data"]]
    assert req_id in requests

def test_approval_assigns_permission(client, admin_token, user_token, test_role, normal_user, db_session):
    from app.identity.models import UserRole
    # Create request
    res = client.post(
        "/access-requests",
        json={
            "requested_role_id": test_role.id,
            "business_justification": "Need access"
        },
        headers={"Authorization": f"Bearer {user_token}"}
    )
    req_id = res.json["data"]["id"]
    
    # Get workflow ID
    from uuid import UUID
    workflow = db_session.query(ApprovalWorkflow).filter_by(access_request_id=UUID(req_id)).first()
    
    # Approve
    approve_res = client.post(
        f"/approval-workflows/{workflow.id}/approve",
        json={"notes": "Approved by admin"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert approve_res.status_code == 200
    
    # Check if user got role
    ur = db_session.query(UserRole).filter_by(user_id=normal_user.id, role_id=test_role.id).first()
    assert ur is not None

def test_request_rejected_no_permission(client, admin_token, user_token, test_role, normal_user, db_session):
    from app.identity.models import UserRole
    res = client.post(
        "/access-requests",
        json={
            "requested_role_id": test_role.id,
            "business_justification": "Need access to reject"
        },
        headers={"Authorization": f"Bearer {user_token}"}
    )
    req_id = res.json["data"]["id"]
    from uuid import UUID
    workflow = db_session.query(ApprovalWorkflow).filter_by(access_request_id=UUID(req_id)).first()
    
    client.post(
        f"/approval-workflows/{workflow.id}/reject",
        json={"notes": "Rejected by admin"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    # User should NOT have role
    ur = db_session.query(UserRole).filter_by(user_id=normal_user.id, role_id=test_role.id).first()
    assert ur is None

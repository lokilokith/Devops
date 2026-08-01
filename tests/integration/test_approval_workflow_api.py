"""Integration tests for Approval Workflow API."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.access_requests.models import AccessRequest, AccessRequestPriority
from app.approval_workflow.models import ApprovalLevel, ApprovalStatus, ApprovalWorkflow
from app.platform.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.identity.models import User

    user = User(
        username="test_user",
        email="test@user.com",
        full_name="Test User",
        employee_id="T01",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_role(db_session):
    from app.roles.models import Role

    role = Role(role_code="TEST_ROLE", role_name="Test Role")
    db_session.add(role)
    db_session.commit()
    return role


@pytest.fixture
def auth_headers(test_user, db_session):
    from app.auth.service import AuthService
    from app.identity.repository import IdentityRepository
    from app.permissions.models import Permission, PermissionAction
    from app.role_permissions.models import RolePermission

    # We must give the user permissions to pass the @requires_permission decorator
    from app.roles.models import Role, RoleType, UserRole

    role = Role(role_code="AUTH_ROLE", role_name="Auth Role", role_type=RoleType.CUSTOM)
    db_session.add(role)
    db_session.flush()

    perms = ["read", "approve", "reject", "cancel"]
    for p in perms:
        perm = Permission(
            permission_code=f"PERM_APPROVAL_WORKFLOWS_{p.upper()}",
            permission_name=f"approval_workflows.{p}",
            action=PermissionAction(p),
        )
        db_session.add(perm)
        db_session.flush()
        db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    ar_perm = Permission(
        permission_code="PERM_ACCESS_REQUESTS_READ",
        permission_name="access_requests.read",
        action=PermissionAction("read"),
    )
    db_session.add(ar_perm)
    db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=ar_perm.id))

    db_session.add(UserRole(user_id=test_user.id, role_id=role.id))
    db_session.commit()

    auth_svc = AuthService(IdentityRepository(db_session))
    token = auth_svc.generate_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_workflow(app, db_session, test_user, test_role):
    ar = AccessRequest(
        request_number="AR-INT-001",
        requester_id=test_user.id,
        requested_role_id=test_role.id,
        business_justification="Test",
        priority=AccessRequestPriority.LOW,
    )
    db_session.add(ar)
    db_session.flush()

    wf = ApprovalWorkflow(
        access_request_id=ar.id,
        approver_id=test_user.id,
        approval_level=ApprovalLevel.MANAGER,
        status=ApprovalStatus.PENDING,
    )
    db_session.add(wf)
    db_session.commit()
    return wf


def test_get_approval_workflows(client, auth_headers, test_workflow):
    response = client.get("/approval-workflows", headers=auth_headers)
    if response.status_code != 200:
        print("ERROR RESPONSE:", response.json)
    assert response.status_code == 200
    assert response.json["success"] is True
    assert len(response.json["data"]) > 0
    assert response.json["data"][0]["id"] == str(test_workflow.id)


def test_get_approval_workflow_by_id(client, auth_headers, test_workflow):
    response = client.get(
        f"/approval-workflows/{test_workflow.id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["data"]["id"] == str(test_workflow.id)


def test_approve_workflow(client, auth_headers, test_workflow):
    response = client.post(
        f"/approval-workflows/{test_workflow.id}/approve",
        json={"comments": "LGTM"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["data"]["status"] == "approved"


def test_reject_workflow_after_approve_fails(client, auth_headers, test_workflow):
    # First approve
    client.post(
        f"/approval-workflows/{test_workflow.id}/approve",
        json={"comments": "LGTM"},
        headers=auth_headers,
    )

    # Try to reject
    response = client.post(
        f"/approval-workflows/{test_workflow.id}/reject",
        json={"comments": "Wait no"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert "Invalid transition" in response.json["errors"][0]


def test_get_workflows_for_request(client, auth_headers, test_workflow):
    response = client.get(
        f"/access-requests/{test_workflow.access_request_id}/approval-workflow",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json["success"] is True
    assert len(response.json["data"]) > 0

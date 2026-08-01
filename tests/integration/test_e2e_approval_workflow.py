"""End-to-End Test for Approval Workflow using Pytest."""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.access_requests.repository import AccessRequestRepository
from app.approval_workflow.models import ApprovalLevel, ApprovalStatus, ApprovalWorkflow
from app.approval_workflow.repository import ApprovalWorkflowRepository
from app.approval_workflow.service import ApprovalWorkflowService
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.auth.service import AuthService
from app.identity.models import User
from app.identity.repository import IdentityRepository
from app.permissions.models import Permission, PermissionAction
from app.role_permissions.models import RolePermission
from app.roles.models import Role, RoleType, UserRole
from app.user_roles.repository import UserRolesRepository


def test_e2e_approval_workflow_full_lifecycle(client, db_session):
    # 1. Setup Data

    # Create Admin/Approver user
    admin_user = User(
        username="e2e_admin",
        email="admin@e2e.com",
        full_name="Admin E2E",
        employee_id="A01",
    )
    db_session.add(admin_user)

    # Create standard user
    standard_user = User(
        username="e2e_user",
        email="user@e2e.com",
        full_name="Standard E2E",
        employee_id="S01",
    )
    db_session.add(standard_user)

    # Create role that standard user will request
    target_role = Role(role_code="E2E_TARGET_ROLE", role_name="E2E Target Role")
    db_session.add(target_role)

    # Create roles with permissions for the tests
    admin_role = Role(
        role_code="E2E_ADMIN_ROLE",
        role_name="E2E Admin Role",
        role_type=RoleType.CUSTOM,
    )
    user_role = Role(
        role_code="E2E_USER_ROLE", role_name="E2E User Role", role_type=RoleType.CUSTOM
    )
    db_session.add(admin_role)
    db_session.add(user_role)
    db_session.flush()

    # Add permissions to admin role
    perms = ["read", "approve", "reject", "cancel"]
    for p in perms:
        perm = Permission(
            permission_code=f"PERM_APPROVAL_WORKFLOWS_{p.upper()}",
            permission_name=f"approval_workflows.{p}",
            action=PermissionAction(p),
        )
        db_session.add(perm)
        db_session.flush()
        db_session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

    ar_read_perm = Permission(
        permission_code="PERM_ACCESS_REQUESTS_READ",
        permission_name="access_requests.read",
        action=PermissionAction("read"),
    )
    ar_create_perm = Permission(
        permission_code="PERM_ACCESS_REQUESTS_CREATE",
        permission_name="access_requests.create",
        action=PermissionAction("create"),
    )
    db_session.add(ar_read_perm)
    db_session.add(ar_create_perm)
    db_session.flush()
    db_session.add(RolePermission(role_id=admin_role.id, permission_id=ar_read_perm.id))

    # Add permissions to standard user role
    db_session.add(
        RolePermission(role_id=user_role.id, permission_id=ar_create_perm.id)
    )
    db_session.add(RolePermission(role_id=user_role.id, permission_id=ar_read_perm.id))

    # Assign roles to users
    db_session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
    db_session.add(UserRole(user_id=standard_user.id, role_id=user_role.id))
    db_session.commit()

    auth_svc = AuthService(IdentityRepository(db_session))
    admin_token = auth_svc.generate_access_token(admin_user.id)
    user_token = auth_svc.generate_access_token(standard_user.id)

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 2. Standard user creates an access request
    response = client.post(
        "/access-requests",
        json={
            "business_justification": "I need E2E access",
            "requested_role_id": str(target_role.id),
            "priority": "high",
        },
        headers=user_headers,
    )
    assert response.status_code == 201
    assert response.json["success"] is True
    request_id = response.json["data"]["id"]

    # 3. Create Approval Workflow (this would normally be done via event/trigger, but we simulate it)

    wf_svc = ApprovalWorkflowService(
        ApprovalWorkflowRepository(db_session),
        AccessRequestRepository(db_session),
        UserRolesRepository(db_session),
        AuditService(AuditRepository(db_session)),
        db_session,
    )
    wf = wf_svc.create_initial_workflow(UUID(request_id), approver_id=admin_user.id)
    assert wf.status.value == "pending"

    # 4. Admin views the pending workflow
    response = client.get(f"/approval-workflows/{wf.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json["data"]["status"] == "pending"

    # 5. Admin approves the workflow
    response = client.post(
        f"/approval-workflows/{wf.id}/approve",
        json={"comments": "Approved!"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json["data"]["status"] == "approved"

    # 6. Verify role provisioning via API or DB
    ur = (
        db_session.query(UserRole)
        .filter_by(user_id=standard_user.id, role_id=target_role.id)
        .first()
    )
    assert ur is not None
    assert ur.assigned_by_user_id == admin_user.id

    # 7. Verify Access Request status is APPROVED
    response = client.get(f"/access-requests/{request_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json["data"]["status"] == "approved"

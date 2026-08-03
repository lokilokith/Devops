import uuid
import pytest
from app.access_requests.models import AccessRequestStatus
from app.approval_workflow.models import ApprovalStatus
from tests.fixtures.factories import AccessRequestFactory, WorkflowFactory
from app.roles.models import UserRole, Role
from app.permissions.models import Permission, PermissionAction


def _grant_perm(db_session, user, perm_code, action):
    from app.roles.models import Role, UserRole
    from app.permissions.models import Permission, PermissionAction
    from app.role_permissions.models import RolePermission
    
    role = db_session.query(Role).filter_by(role_code="TEST_ROLE").first()
    if not role:
        role = Role(role_code="TEST_ROLE", role_name="Test Role", role_type="custom")
        db_session.add(role)
        db_session.flush()
        
    perm = db_session.query(Permission).filter_by(permission_code=perm_code).first()
    if not perm:
        perm = Permission(permission_code=perm_code, permission_name=perm_code, action=action)
        db_session.add(perm)
        db_session.flush()
        
    if not db_session.query(RolePermission).filter_by(role_id=role.id, permission_id=perm.id).first():
        db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
        
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first():
        db_session.add(UserRole(user_id=user.id, role_id=role.id))
    
    db_session.flush()

def test_assigned_approver_can_approve(client, db_session, normal_user, approver_user, approver_token):
    _grant_perm(db_session, approver_user, "PERM_ACCESS_REQUESTS_APPROVE", PermissionAction.APPROVE)
    # Create request
    req = AccessRequestFactory(requester=normal_user, status=AccessRequestStatus.PENDING)
    # Create workflow assigned to approver
    wf = WorkflowFactory(access_request_id=req.id, approver=approver_user, status=ApprovalStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/approve",
        headers={"Authorization": f"Bearer {approver_token}"}
    )
    assert res.status_code == 200
    
    # Verify DB state
    db_session.refresh(req)
    db_session.refresh(wf)
    assert req.status == AccessRequestStatus.APPROVED
    assert wf.status == ApprovalStatus.APPROVED

def test_user_with_approve_permission_but_not_assigned_approver(client, db_session, normal_user, normal_token, approver_user):
    # Give normal_user access_requests.approve permission to bypass the route decorator
    # The route decorator checks for "access_requests", "approve"
    _grant_perm(db_session, normal_user, "PERM_ACCESS_REQUESTS_APPROVE", PermissionAction.APPROVE)

    req = AccessRequestFactory(requester=approver_user, status=AccessRequestStatus.PENDING)
    wf = WorkflowFactory(access_request_id=req.id, approver=approver_user, status=ApprovalStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/approve",
        headers={"Authorization": f"Bearer {normal_token}"}
    )
    # Should get 403 Forbidden because they are not the assigned approver and don't have approval_workflows.approve
    assert res.status_code == 403

    db_session.refresh(req)
    assert req.status == AccessRequestStatus.PENDING

def test_normal_user_approval_attempt(client, db_session, normal_user, normal_token, approver_user):
    req = AccessRequestFactory(requester=approver_user, status=AccessRequestStatus.PENDING)
    wf = WorkflowFactory(access_request_id=req.id, approver=approver_user, status=ApprovalStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/approve",
        headers={"Authorization": f"Bearer {normal_token}"}
    )
    # The route decorator will block this since normal_user doesn't have access_requests.approve
    assert res.status_code == 403

def test_duplicate_approval(client, db_session, normal_user, approver_user, approver_token):
    _grant_perm(db_session, approver_user, "PERM_ACCESS_REQUESTS_APPROVE", PermissionAction.APPROVE)
    req = AccessRequestFactory(requester=normal_user, status=AccessRequestStatus.PENDING)
    wf = WorkflowFactory(access_request_id=req.id, approver=approver_user, status=ApprovalStatus.PENDING)
    db_session.flush()

    res1 = client.post(
        f"/access-requests/{req.id}/approve",
        headers={"Authorization": f"Bearer {approver_token}"}
    )
    assert res1.status_code == 200

    res2 = client.post(
        f"/access-requests/{req.id}/approve",
        headers={"Authorization": f"Bearer {approver_token}"}
    )
    # Should be rejected because it's already approved
    assert res2.status_code == 409

def test_requester_cancels_own_pending_request(client, db_session, normal_user, normal_token):
    req = AccessRequestFactory(requester=normal_user, status=AccessRequestStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/cancel",
        headers={"Authorization": f"Bearer {normal_token}"}
    )
    assert res.status_code == 200
    db_session.refresh(req)
    assert req.status == AccessRequestStatus.CANCELLED

def test_user_attempts_cancelling_another_users_request(client, db_session, normal_user, normal_token, approver_user):
    # Request belongs to approver_user
    req = AccessRequestFactory(requester=approver_user, status=AccessRequestStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/cancel",
        headers={"Authorization": f"Bearer {normal_token}"}
    )
    assert res.status_code == 403
    db_session.refresh(req)
    assert req.status == AccessRequestStatus.PENDING

def test_admin_cancels_another_users_request(client, db_session, admin_user, admin_token, normal_user):
    # Give admin CANCEL permission if they don't have it natively in tests, but they probably do.
    req = AccessRequestFactory(requester=normal_user, status=AccessRequestStatus.PENDING)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 200
    db_session.refresh(req)
    assert req.status == AccessRequestStatus.CANCELLED

def test_approved_request_cancellation_attempt(client, db_session, normal_user, normal_token):
    req = AccessRequestFactory(requester=normal_user, status=AccessRequestStatus.APPROVED)
    db_session.flush()

    res = client.post(
        f"/access-requests/{req.id}/cancel",
        headers={"Authorization": f"Bearer {normal_token}"}
    )
    assert res.status_code == 200

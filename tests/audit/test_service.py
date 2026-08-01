from unittest.mock import patch
from uuid import uuid4

import pytest

from app.audit.models import AuditSeverity, AuditStatus


def test_log_login(audit_service, audit_repo):
    uid = uuid4()
    audit_service.log_login(uid, AuditStatus.SUCCESS, "127.0.0.1")

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "LOGIN"
    assert logs[0].severity == AuditSeverity.INFO

    audit_service.log_login(uid, AuditStatus.FAILED, "127.0.0.1")
    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 2
    assert (
        logs[0].severity == AuditSeverity.HIGH
    )  # Order by desc timestamp, failed is latest


def test_log_role_assignment(audit_service, audit_repo):
    uid = uuid4()
    tid = uuid4()
    rid = uuid4()
    audit_service.log_role_assignment(uid, tid, rid, AuditStatus.SUCCESS)

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "ASSIGN_ROLE"


def test_log_permission_assignment(audit_service, audit_repo):
    uid = uuid4()
    rid = uuid4()
    pid = uuid4()
    audit_service.log_permission_assignment(uid, rid, pid, AuditStatus.SUCCESS)

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "ASSIGN_PERMISSION"
    assert logs[0].details["role_id"] == str(rid)


def test_log_access_request(audit_service, audit_repo):
    uid = uuid4()
    rid = uuid4()
    audit_service.log_access_request(uid, rid, AuditStatus.SUCCESS)

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "SUBMIT_ACCESS_REQUEST"


def test_log_approval(audit_service, audit_repo):
    uid = uuid4()
    aid = uuid4()
    audit_service.log_approval(uid, aid, AuditStatus.SUCCESS)

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "PROCESS_APPROVAL"


def test_log_authorization_denied(audit_service, audit_repo):
    uid = uuid4()
    audit_service.log_authorization_denied(uid, "RES1", "READ")

    logs = audit_repo.filter_by_user(uid)
    assert len(logs) == 1
    assert logs[0].action == "AUTHORIZATION_DENIED"
    assert logs[0].details["permission_action"] == "READ"


def test_log_event_swallows_exception(audit_service, audit_repo):
    # Ensure it doesn't raise exception
    with patch.object(audit_repo, "create_log", side_effect=Exception("mocked error")):
        res = audit_service.log_login(uuid4(), AuditStatus.SUCCESS)
        assert res is None

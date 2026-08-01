import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.audit.models import AuditLog, AuditStatus, AuditSeverity
from app.audit.exceptions import AuditRepositoryError


def test_create_and_get(audit_repo):
    log = AuditLog(
        event_id="EVT-123",
        timestamp=datetime.now(timezone.utc),
        actor_user_id=uuid4(),
        action="TEST_ACTION",
        resource_type="TEST_RESOURCE",
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.INFO,
    )
    created = audit_repo.create_log(log)
    assert created.id is not None

    fetched = audit_repo.get_by_id(created.id)
    assert fetched.event_id == "EVT-123"

    fetched_evt = audit_repo.get_by_event_id("EVT-123")
    assert fetched_evt.id == created.id


def test_list_and_count(audit_repo):
    uid = uuid4()
    audit_repo.create_log(
        AuditLog(
            event_id="EVT-L1",
            timestamp=datetime.now(timezone.utc),
            actor_user_id=uid,
            action="A1",
            resource_type="R1",
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
    )
    audit_repo.create_log(
        AuditLog(
            event_id="EVT-L2",
            timestamp=datetime.now(timezone.utc),
            actor_user_id=uid,
            action="A2",
            resource_type="R1",
            status=AuditStatus.FAILED,
            severity=AuditSeverity.HIGH,
        )
    )

    assert audit_repo.count() >= 2
    assert audit_repo.count(actor_user_id=uid) == 2
    assert audit_repo.count(status=AuditStatus.FAILED) == 1

    lst = audit_repo.list_logs()
    assert len(lst) >= 2


def test_filters(audit_repo):
    uid1 = uuid4()
    uid2 = uuid4()
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=2)

    audit_repo.create_log(
        AuditLog(
            event_id="EVT-F1",
            timestamp=now,
            actor_user_id=uid1,
            action="LOGIN",
            resource_type="SYSTEM",
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
    )
    audit_repo.create_log(
        AuditLog(
            event_id="EVT-F2",
            timestamp=past,
            actor_user_id=uid2,
            action="LOGOUT",
            resource_type="SYSTEM",
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
    )

    u_logs = audit_repo.filter_by_user(uid1)
    assert len(u_logs) == 1

    a_logs = audit_repo.filter_by_action("LOGIN")
    assert len(a_logs) == 1

    d_logs = audit_repo.filter_by_date_range(
        past - timedelta(hours=1), past + timedelta(hours=1)
    )
    assert len(d_logs) == 1
    assert d_logs[0].event_id == "EVT-F2"

    s_logs = audit_repo.search(severity=AuditSeverity.INFO)
    assert len(s_logs) == 2


def test_sqlalchemy_errors(audit_repo):
    log = AuditLog(
        event_id="EVT-ERR",
        timestamp=datetime.now(timezone.utc),
        actor_user_id=uuid4(),
        action="TEST_ACTION",
        resource_type="TEST_RESOURCE",
        status=AuditStatus.SUCCESS,
        severity=AuditSeverity.INFO,
    )

    with patch.object(
        audit_repo._session, "add", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.create_log(log)

    with patch.object(
        audit_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.get_by_id(uuid4())

    with patch.object(
        audit_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.get_by_event_id("evt")

    with patch.object(
        audit_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.list_logs()

    with patch.object(
        audit_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.search()

    with patch.object(
        audit_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(AuditRepositoryError):
            audit_repo.count()

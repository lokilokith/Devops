"""Unit tests for Phase 8 helper session registration and termination."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch
from uuid import uuid4

import pytest

import app.execution.helper.opsforge_helper as helper


@pytest.fixture
def temp_helper_env(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    manifest_path = os.path.join(temp_dir, "ownership_manifest.json")
    sessions_path = os.path.join(temp_dir, "sessions.json")
    sudoers_dir = os.path.join(temp_dir, "sudoers.d")
    audit_log = os.path.join(temp_dir, "helper.log")

    os.makedirs(sudoers_dir, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": 1,
                "managed_accounts": [
                    {"username": "u_testuser", "provisioned_at": "2026-08-31T00:00:00Z"}
                ],
            },
            f,
        )

    monkeypatch.setattr(helper, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(helper, "MANIFEST_DIR", temp_dir)
    monkeypatch.setattr(helper, "SESSIONS_PATH", sessions_path)
    monkeypatch.setattr(helper, "SUDOERS_DIR", sudoers_dir)
    monkeypatch.setattr(helper, "AUDIT_LOG_PATH", audit_log)

    return {
        "dir": temp_dir,
        "manifest": manifest_path,
        "sessions": sessions_path,
        "sudoers": sudoers_dir,
    }


def test_register_session_success(temp_helper_env):
    grant_id = str(uuid4())
    session_id = str(uuid4())
    account = "u_testuser"
    pid_str = "54321"

    # Mock pwd and proc identity
    class MockPw:
        pw_uid = 1001

    with (
        patch.object(helper, "_get_pwnam", return_value=MockPw()),
        patch.object(
            helper,
            "_get_process_identity",
            return_value={"pid": 54321, "uid": 1001, "starttime": "123456"},
        ),
    ):
        res = helper.register_session(grant_id, session_id, account, pid_str)

    assert res["session_id"] == session_id
    assert res["grant_id"] == grant_id
    assert res["status"] == "ACTIVE"
    assert res["uid"] == 1001

    # Check persisted registry
    sessions_data = helper.load_sessions()
    assert len(sessions_data["sessions"]) == 1
    assert sessions_data["sessions"][0]["session_id"] == session_id


def test_register_session_uid_mismatch_fails_closed(temp_helper_env):
    grant_id = str(uuid4())
    session_id = str(uuid4())
    account = "u_testuser"

    class MockPw:
        pw_uid = 1001

    # Process belongs to root or another user (UID 0 != 1001)
    with (
        patch.object(helper, "_get_pwnam", return_value=MockPw()),
        patch.object(
            helper,
            "_get_process_identity",
            return_value={"pid": 54321, "uid": 0, "starttime": "123456"},
        ),
    ):
        with pytest.raises(
            helper.HelperSecurityError, match="Security violation.*owned by UID 0"
        ):
            helper.register_session(grant_id, session_id, account, "54321")


def test_terminate_jit_sessions_pid_reuse_safety(temp_helper_env):
    grant_id = str(uuid4())
    session_id = str(uuid4())
    account = "u_testuser"

    # Pre-register session with original UID 1001 and starttime "123456"
    sessions_data = {
        "schema_version": 1,
        "sessions": [
            {
                "session_id": session_id,
                "grant_id": grant_id,
                "account": account,
                "uid": 1001,
                "pid": 54321,
                "starttime": "123456",
                "status": "ACTIVE",
            }
        ],
    }
    helper.save_sessions(sessions_data)

    # Simulate PID reuse: PID 54321 now has starttime "999999" (new process spawned with same PID)
    with (
        patch("os.path.exists", return_value=True),
        patch.object(
            helper,
            "_get_process_identity",
            return_value={"pid": 54321, "uid": 1001, "starttime": "999999"},
        ),
        patch("os.kill") as mock_kill,
    ):
        res = helper.terminate_jit_sessions(grant_id)

    # Process must NOT be killed!
    mock_kill.assert_not_called()
    assert 54321 in res["reused_pids"]
    assert len(res["terminated_pids"]) == 0

    # Registry updated to mark PID_REUSED_UNKNOWN
    updated_sessions = helper.load_sessions()["sessions"]
    assert updated_sessions[0]["status"] == "PID_REUSED_UNKNOWN"


def test_terminate_jit_sessions_verified_kill(temp_helper_env):
    grant_id = str(uuid4())
    session_id = str(uuid4())
    account = "u_testuser"
    pid = 54321

    sessions_data = {
        "schema_version": 1,
        "sessions": [
            {
                "session_id": session_id,
                "grant_id": grant_id,
                "account": account,
                "uid": 1001,
                "pid": pid,
                "starttime": "123456",
                "status": "ACTIVE",
            }
        ],
    }
    helper.save_sessions(sessions_data)

    kill_calls = []

    def mock_kill_func(p, sig):
        kill_calls.append((p, sig))
        if sig == 0 and len(kill_calls) > 1:
            # Process terminated after signal
            raise ProcessLookupError("No such process")
        return None

    with (
        patch("os.path.exists", return_value=True),
        patch.object(
            helper,
            "_get_process_identity",
            return_value={"pid": pid, "uid": 1001, "starttime": "123456"},
        ),
        patch("os.kill", side_effect=mock_kill_func),
    ):
        res = helper.terminate_jit_sessions(grant_id)

    assert pid in res["terminated_pids"]
    updated_sessions = helper.load_sessions()["sessions"]
    assert updated_sessions[0]["status"] == "TERMINATED"

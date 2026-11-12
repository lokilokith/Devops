"""Comprehensive unit tests for opsforge_helper operations, rollback, and CLI dispatch."""

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from app.execution.helper.opsforge_helper import (
    HelperExecutionError,
    HelperSecurityError,
    _get_euid,
    _get_uid,
    add_account_to_manifest,
    add_jit_grant,
    is_account_managed,
    load_manifest,
    log_audit_event,
    main,
    provision_account,
    remove_account,
    remove_jit_grant,
)


def test_helper_uid_euid_helpers():
    """Test _get_uid and _get_euid return integers."""
    assert isinstance(_get_uid(), int)
    assert isinstance(_get_euid(), int)


def test_log_audit_event_fallback(tmp_path, monkeypatch):
    """Test log_audit_event records to custom audit log path."""
    audit_file = str(tmp_path / "audit.log")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.AUDIT_LOG_PATH", audit_file
    )

    log_audit_event("provision_account", "SUCCESS", {"account": "test_user"})

    assert os.path.exists(audit_file)
    with open(audit_file, "r", encoding="utf-8") as f:
        line = f.readline()
        entry = json.loads(line)
        assert entry["operation"] == "provision_account"
        assert entry["status"] == "SUCCESS"
        assert entry["details"]["account"] == "test_user"


def test_log_audit_event_with_error(tmp_path, monkeypatch):
    """Test log_audit_event records error message."""
    audit_file = str(tmp_path / "audit.log")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.AUDIT_LOG_PATH", audit_file
    )

    log_audit_event(
        "remove_account", "FAILED", {"account": "test_user"}, "User not found"
    )

    with open(audit_file, "r", encoding="utf-8") as f:
        entry = json.loads(f.readline())
        assert entry["status"] == "FAILED"
        assert entry["error"] == "User not found"


def test_load_manifest_corrupted_structure(tmp_path, monkeypatch):
    """Test corrupted manifest raises HelperSecurityError."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    with open(manifest_file, "w", encoding="utf-8") as f:
        f.write('{"bad_key": 123}')

    with pytest.raises(HelperSecurityError, match="Corrupted ownership manifest"):
        load_manifest()


def test_load_manifest_invalid_json(tmp_path, monkeypatch):
    """Test invalid JSON in manifest raises HelperExecutionError."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    with open(manifest_file, "w", encoding="utf-8") as f:
        f.write("not json")

    with pytest.raises(HelperExecutionError, match="Failed to read ownership manifest"):
        load_manifest()


def test_provision_account_unmanaged_os_user_rejected(tmp_path, monkeypatch):
    """Test attempting to provision an unmanaged OS user is rejected."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    # Mock user exists in OS
    fake_pw = MagicMock(
        pw_name="existing_user",
        pw_uid=1001,
        pw_gid=1001,
        pw_dir=str(tmp_path),
        pw_shell="/bin/bash",
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper._get_pwnam", lambda u: fake_pw
    )

    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    with pytest.raises(HelperSecurityError, match="exists in OS but is NOT managed"):
        provision_account("existing_user", key)


def test_provision_account_success_mocked(tmp_path, monkeypatch):
    """Test full provision_account flow with mocked subprocess and file system."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    home_dir = str(tmp_path / "home_test")
    os.makedirs(home_dir, exist_ok=True)
    fake_pw = MagicMock(
        pw_name="test_user",
        pw_uid=1001,
        pw_gid=1001,
        pw_dir=home_dir,
        pw_shell="/bin/bash",
    )

    # First lookup raises KeyError (user not existing yet), second returns fake_pw
    lookup_count = 0

    def mock_pwnam(name):
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            raise KeyError("User not found")
        return fake_pw

    monkeypatch.setattr("app.execution.helper.opsforge_helper._get_pwnam", mock_pwnam)

    def mock_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    provision_account("test_user", key)

    assert is_account_managed("test_user")
    auth_keys_path = os.path.join(home_dir, ".ssh", "authorized_keys")
    assert os.path.exists(auth_keys_path)


def test_provision_account_useradd_failure(tmp_path, monkeypatch):
    """Test useradd failure raises HelperExecutionError."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper._get_pwnam",
        MagicMock(side_effect=KeyError("User not found")),
    )

    def mock_run_fail(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="useradd: permission denied"
        )

    monkeypatch.setattr(subprocess, "run", mock_run_fail)

    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    with pytest.raises(HelperExecutionError, match="useradd failed"):
        provision_account("test_user", key)


def test_remove_account_unmanaged_rejected(tmp_path, monkeypatch):
    """Test removing an account not in manifest raises HelperSecurityError."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    with pytest.raises(HelperSecurityError, match="not recorded as OpsForge-owned"):
        remove_account("unmanaged_user")


def test_remove_account_success_mocked(tmp_path, monkeypatch):
    """Test successful removal cleans JIT drop-ins, user, and manifest."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    sudoers_dir = str(tmp_path / "sudoers.d")
    os.makedirs(sudoers_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )
    monkeypatch.setattr("app.execution.helper.opsforge_helper.SUDOERS_DIR", sudoers_dir)

    add_account_to_manifest("test_user")

    # Create dummy jit file for user
    jit_file = os.path.join(
        sudoers_dir, "opsforge-jit-550e8400-e29b-41d4-a716-446655440000"
    )
    with open(jit_file, "w") as f:
        f.write("test_user ALL=(ALL) NOPASSWD: /bin/ls")

    pwnam_calls = 0

    def mock_pwnam(name):
        nonlocal pwnam_calls
        pwnam_calls += 1
        if pwnam_calls == 1:
            return MagicMock(pw_name="test_user")
        raise KeyError("User deleted")

    monkeypatch.setattr("app.execution.helper.opsforge_helper._get_pwnam", mock_pwnam)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, *a, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        ),
    )

    remove_account("test_user")

    assert not is_account_managed("test_user")
    assert not os.path.exists(jit_file)


def test_add_jit_grant_success_mocked(tmp_path, monkeypatch):
    """Test add_jit_grant writes validated sudoers file and verifies."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    sudoers_dir = str(tmp_path / "sudoers.d")
    os.makedirs(sudoers_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )
    monkeypatch.setattr("app.execution.helper.opsforge_helper.SUDOERS_DIR", sudoers_dir)

    add_account_to_manifest("test_user")

    def mock_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="OK", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    grant_id = "550e8400-e29b-41d4-a716-446655440000"
    add_jit_grant(grant_id, "test_user", "system_health_check")

    target_file = os.path.join(sudoers_dir, f"opsforge-jit-{grant_id}")
    assert os.path.exists(target_file)
    with open(target_file, "r") as f:
        content = f.read()
        assert "test_user" in content
        assert "/usr/bin/uptime" in content


def test_add_jit_grant_visudo_failure(tmp_path, monkeypatch):
    """Test visudo failure deletes temp file and fails closed."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    sudoers_dir = str(tmp_path / "sudoers.d")
    os.makedirs(sudoers_dir, exist_ok=True)
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )
    monkeypatch.setattr("app.execution.helper.opsforge_helper.SUDOERS_DIR", sudoers_dir)

    add_account_to_manifest("test_user")

    def mock_run(cmd, *args, **kwargs):
        if "visudo" in cmd[0]:
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="syntax error in sudoers"
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    grant_id = "550e8400-e29b-41d4-a716-446655440000"
    with pytest.raises(HelperExecutionError, match="visudo validation failed"):
        add_jit_grant(grant_id, "test_user", "system_health_check")

    target_file = os.path.join(sudoers_dir, f"opsforge-jit-{grant_id}")
    assert not os.path.exists(target_file)


def test_remove_jit_grant_success_mocked(tmp_path, monkeypatch):
    """Test remove_jit_grant removes drop-in file."""
    sudoers_dir = str(tmp_path / "sudoers.d")
    os.makedirs(sudoers_dir, exist_ok=True)
    monkeypatch.setattr("app.execution.helper.opsforge_helper.SUDOERS_DIR", sudoers_dir)

    grant_id = "550e8400-e29b-41d4-a716-446655440000"
    target_file = os.path.join(sudoers_dir, f"opsforge-jit-{grant_id}")
    with open(target_file, "w") as f:
        f.write("dummy")

    remove_jit_grant(grant_id)
    assert not os.path.exists(target_file)


def test_main_cli_dispatch(monkeypatch, capsys):
    """Test main() CLI argument parsing and dispatch."""
    # 1. No arguments
    monkeypatch.setattr(sys, "argv", ["opsforge-helper"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

    # 2. Disallowed operation
    monkeypatch.setattr(sys, "argv", ["opsforge-helper", "reboot"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

    # 3. Invalid argument counts
    monkeypatch.setattr(sys, "argv", ["opsforge-helper", "provision_account"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["opsforge-helper", "remove_account"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["opsforge-helper", "add_jit_grant"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["opsforge-helper", "remove_jit_grant"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1

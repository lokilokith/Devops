"""Unit tests for opsforge_helper functions and validation policies."""

import pytest

from app.execution.helper.opsforge_helper import (
    COMMAND_CATALOG,
    PROTECTED_SYSTEM_ACCOUNTS,
    HelperSecurityError,
    add_account_to_manifest,
    is_account_managed,
    load_manifest,
    remove_account_from_manifest,
    validate_account_name,
    validate_command_set_id,
    validate_grant_id,
    validate_public_key,
)


def test_validate_account_name_valid():
    """Test valid POSIX compliant account names."""
    valid_names = ["user_1", "johndoe", "alice-adm", "app_svc", "dev01", "ops_user"]
    for name in valid_names:
        validate_account_name(name)  # Should not raise


def test_validate_account_name_protected_rejected():
    """Test protected system accounts are strictly rejected."""
    for protected in PROTECTED_SYSTEM_ACCOUNTS:
        with pytest.raises(HelperSecurityError, match="protected system account"):
            validate_account_name(protected)


def test_validate_account_name_invalid_syntax():
    """Test invalid characters, spaces, shell metacharacters, uppercase are rejected."""
    invalid_names = [
        "User1",  # Uppercase
        "user;id",  # Command injection
        "user|sh",  # Pipe
        "../admin",  # Traversal
        "user name",  # Space
        "user$var",  # Variable expansion
        "123user",  # Starts with number
        "-user",  # Starts with hyphen
        "",  # Empty
        "a" * 35,  # Too long (>32)
    ]
    for invalid in invalid_names:
        with pytest.raises(HelperSecurityError):
            validate_account_name(invalid)


def test_validate_public_key_valid():
    """Test valid OpenSSH public keys pass validation."""
    valid_keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@host",
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC3ValidRSAKeyDataHere12345678901234567890123456789012345678901234567890123456789012345678901234567890",
        "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMKeyData987654321098765432101234567890 user@host",
    ]
    for key in valid_keys:
        validate_public_key(key)  # Should not raise


def test_validate_public_key_injection_rejected():
    """Test public keys with newlines, control characters, or invalid payloads are rejected."""
    invalid_keys = [
        'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI1234567\ncommand="/bin/sh" ssh-rsa AAAAB3...',  # Newline injection
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI1234567\r\necho injected",
        "ssh-unsupported AAAAC3NzaC1lZDI1NTE5AAAAI12345",  # Unsupported key type
        "ssh-ed25519 !!!NOT_BASE64!!!",  # Malformed base64
        "",  # Empty
        "ssh-ed25519 AAAA",  # Too short payload
    ]
    for key in invalid_keys:
        with pytest.raises(HelperSecurityError):
            validate_public_key(key)


def test_validate_grant_id():
    """Test grant ID requires strict UUID format."""
    valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
    validate_grant_id(valid_uuid)  # Should not raise

    invalid_uuids = [
        "550e8400",
        "../traversal",
        "550e8400-e29b-41d4-a716-446655440000; rm -rf /",
        "not-a-uuid",
    ]
    for invalid in invalid_uuids:
        with pytest.raises(HelperSecurityError, match="Must be a valid UUID"):
            validate_grant_id(invalid)

    with pytest.raises(
        HelperSecurityError, match="Grant ID must be a non-empty string"
    ):
        validate_grant_id("")


def test_validate_command_set_id():
    """Test command set ID must exist in strict catalog."""
    for cmd_set in COMMAND_CATALOG:
        cmds = validate_command_set_id(cmd_set)
        assert isinstance(cmds, list)
        assert len(cmds) > 0

    invalid_cmd_sets = [
        "all",
        "sudo_all",
        "custom_command",
        "ALL",
    ]
    for invalid in invalid_cmd_sets:
        with pytest.raises(HelperSecurityError, match="Unknown command set ID"):
            validate_command_set_id(invalid)

    with pytest.raises(
        HelperSecurityError, match="Command set ID must be a non-empty string"
    ):
        validate_command_set_id("")


def test_manifest_management(tmp_path, monkeypatch):
    """Test manifest load, save, add, and remove operations."""
    manifest_file = str(tmp_path / "ownership_manifest.json")
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_PATH", manifest_file
    )
    monkeypatch.setattr(
        "app.execution.helper.opsforge_helper.MANIFEST_DIR", str(tmp_path)
    )

    # Initial load of non-existent manifest returns empty structure
    manifest = load_manifest()
    assert manifest["schema_version"] == 1
    assert manifest["managed_accounts"] == []
    assert not is_account_managed("test_user_1")

    # Add account
    add_account_to_manifest("test_user_1")
    assert is_account_managed("test_user_1")

    # Add duplicate account is idempotent
    add_account_to_manifest("test_user_1")
    manifest = load_manifest()
    assert len(manifest["managed_accounts"]) == 1

    # Remove account
    remove_account_from_manifest("test_user_1")
    assert not is_account_managed("test_user_1")
    manifest = load_manifest()
    assert len(manifest["managed_accounts"]) == 0

"""Tests for deterministic target OS username derivation."""

import pytest

from app.target_accounts.username import (
    MAX_OS_USERNAME_LENGTH,
    derive_target_username,
)


def test_derive_target_username_basic():
    """Test basic deterministic slug derivation."""
    assert derive_target_username("alice") == "alice"
    assert derive_target_username("bob.smith") == "bob_smith"
    assert derive_target_username("charlie-dev") == "charlie-dev"
    assert derive_target_username("dave_123") == "dave_123"


def test_derive_target_username_starts_with_digit_or_symbol():
    """Test username starting with non-letter gets safe prefix."""
    derived = derive_target_username("123user")
    assert derived.startswith("u_")
    assert derive_target_username("-user").startswith("u_")


def test_derive_target_username_protected_system_accounts():
    """Test protected system accounts are never returned verbatim."""
    protected = ["root", "bin", "daemon", "sys", "opsforge-svc", "nobody", "sshd"]
    for name in protected:
        derived = derive_target_username(name)
        assert derived != name
        assert derived.startswith("u_")


def test_derive_target_username_length_bounded():
    """Test username length never exceeds 32 characters."""
    long_username = "a" * 50
    derived = derive_target_username(long_username)
    assert len(derived) <= MAX_OS_USERNAME_LENGTH
    assert len(derived) > 0


def test_derive_target_username_collision_handling():
    """Test deterministic numeric suffix on collision."""
    existing = {"alice", "alice_1", "alice_2"}
    derived = derive_target_username("alice", existing_usernames=existing)
    assert derived == "alice_3"
    assert len(derived) <= MAX_OS_USERNAME_LENGTH


def test_derive_target_username_path_traversal_and_invalid_chars_rejected():
    """Test path traversal, null bytes, and malicious characters are rejected or sanitized."""
    with pytest.raises(ValueError, match="forbidden path traversal"):
        derive_target_username("../alice")

    with pytest.raises(ValueError, match="forbidden path traversal"):
        derive_target_username("alice/../../etc")

    with pytest.raises(ValueError, match="forbidden path traversal"):
        derive_target_username("alice\x00root")

    with pytest.raises(ValueError, match="non-empty"):
        derive_target_username("")

    # Shell metacharacters get sanitized
    derived = derive_target_username("user;rm -rf")
    assert ";" not in derived
    assert " " not in derived
    assert derived == "user_rm_-rf"

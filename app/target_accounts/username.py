"""Deterministic Target OS Username Derivation for OpsForge.

Enforces POSIX-safe naming policy, character sanitization, length bounds,
collision avoidance, and system account protection.
"""

from __future__ import annotations

import re
from typing import Collection, Set

from app.execution.helper.opsforge_helper import (
    ACCOUNT_REGEX,
    PROTECTED_SYSTEM_ACCOUNTS,
)

# Canonical prefix for generated target accounts
TARGET_USER_PREFIX = "u_"
MAX_OS_USERNAME_LENGTH = 32


def derive_target_username(
    control_plane_username: str,
    existing_usernames: Collection[str] = (),
) -> str:
    """Deterministically derive a POSIX-safe, collision-free target OS username.

    Args:
        control_plane_username: The username in the OpsForge Control Plane.
        existing_usernames: Set or sequence of OS usernames already assigned on the target resource.

    Returns:
        A unique, POSIX-safe, non-protected target OS username (<= 32 chars).

    Raises:
        ValueError: If the input username is empty or cannot be sanitized into a valid slug.
    """
    if not control_plane_username or not isinstance(control_plane_username, str):
        raise ValueError("Control plane username must be a non-empty string.")

    # 1. Normalize: lowercase, strip whitespace
    raw = control_plane_username.strip().lower()

    # Reject null bytes and path traversal explicitly
    if "\x00" in raw or "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError(
            "Username contains forbidden path traversal or null characters."
        )

    # 2. Sanitize: replace non-alphanumeric chars (except underscore and hyphen) with underscore
    slug = re.sub(r"[^a-z0-9_-]", "_", raw)
    slug = re.sub(r"_+", "_", slug).strip("_")

    if not slug:
        raise ValueError("Sanitized username slug is empty.")

    # 3. Ensure starts with a valid character ([a-z_])
    if not re.match(r"^[a-z_]", slug):
        slug = f"{TARGET_USER_PREFIX}{slug}"

    # 4. If slug matches a protected system account or does not have prefix, prefix it
    if slug in PROTECTED_SYSTEM_ACCOUNTS:
        slug = f"{TARGET_USER_PREFIX}{slug}"

    # 5. Truncate base slug to leave room for collision suffixes (max 28 chars for base)
    max_base_len = MAX_OS_USERNAME_LENGTH - 4
    if len(slug) > max_base_len:
        slug = slug[:max_base_len].rstrip("_")

    # 6. Ensure valid regex format
    if not ACCOUNT_REGEX.match(slug):
        slug = f"{TARGET_USER_PREFIX}{slug[:max_base_len-2]}"
        if not ACCOUNT_REGEX.match(slug):
            raise ValueError(
                f"Unable to derive POSIX-safe username from '{control_plane_username}'."
            )

    # 7. Collision resolution against existing target usernames
    existing_set: Set[str] = set(existing_usernames)
    candidate = slug

    if candidate not in existing_set and candidate not in PROTECTED_SYSTEM_ACCOUNTS:
        return candidate

    counter = 1
    while True:
        suffix = f"_{counter}"
        avail_len = MAX_OS_USERNAME_LENGTH - len(suffix)
        base_part = slug[:avail_len].rstrip("_")
        candidate = f"{base_part}{suffix}"

        if candidate not in existing_set and candidate not in PROTECTED_SYSTEM_ACCOUNTS:
            return candidate

        counter += 1
        if counter > 9999:
            raise ValueError(f"Exhausted collision namespace for base slug '{slug}'.")

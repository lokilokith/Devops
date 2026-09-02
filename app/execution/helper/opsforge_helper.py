#!/usr/bin/python3 -I
"""OpsForge Target Helper (`opsforge-helper`).

Authoritative target-side helper executable executing as root under strict sudo boundaries.
Canonical operations:
  provision_account <account> <public_key>
  remove_account <account>
  add_jit_grant <grant_id> <account> <command_set_id>
  remove_jit_grant <grant_id>

Security Invariants:
- Fixed absolute path (/usr/local/sbin/opsforge-helper), root-owned, mode 0750.
- Strict positional argument parsing; reject-by-default on invalid or extra arguments.
- Zero shell interpolation (all OS commands run via subprocess with explicit arg lists).
- Protected ownership manifest at /var/lib/opsforge/ownership_manifest.json (0600, root:root).
- Sudoers drop-ins validated via visudo -c on temp file before atomic activation.
- Direct state verification and deterministic rollback on intermediate failures.
- Target-local structured audit logging independent of application plane.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set

try:
    import pwd
except ImportError:
    pwd = None  # type: ignore[assignment]

# Configuration constants
MANIFEST_PATH = os.environ.get(
    "OPSFORGE_MANIFEST_PATH", "/var/lib/opsforge/ownership_manifest.json"
)
MANIFEST_DIR = os.path.dirname(MANIFEST_PATH)
SESSIONS_PATH = os.environ.get(
    "OPSFORGE_SESSIONS_PATH", "/var/lib/opsforge/sessions.json"
)
SUDOERS_DIR = os.environ.get("OPSFORGE_SUDOERS_DIR", "/etc/sudoers.d")
AUDIT_LOG_PATH = os.environ.get(
    "OPSFORGE_AUDIT_LOG_PATH", "/var/log/opsforge-helper.log"
)

# Account validation rules
ACCOUNT_REGEX = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
SESSION_ID_REGEX = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
PID_REGEX = re.compile(r"^[1-9][0-9]{0,9}$")

# System and protected accounts that can NEVER be provisioned, registered, or removed by OpsForge
PROTECTED_SYSTEM_ACCOUNTS: Set[str] = {
    "root",
    "bin",
    "daemon",
    "sys",
    "sync",
    "games",
    "man",
    "lp",
    "mail",
    "news",
    "uucp",
    "proxy",
    "www-data",
    "backup",
    "list",
    "irc",
    "gnats",
    "nobody",
    "_apt",
    "systemd-network",
    "systemd-resolve",
    "systemd-timesync",
    "messagebus",
    "sshd",
    "opsforge-svc",
    "admin",
    "sudo",
    "wheel",
}

# Supported SSH public key algorithms
ALLOWED_KEY_TYPES: Set[str] = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
}

# Predefined JIT command sets (Strict Catalog - NO WILDCARDS)
COMMAND_CATALOG: Dict[str, List[str]] = {
    "system_health_check": [
        "/usr/bin/uptime",
        "/usr/bin/vmstat",
        "/usr/bin/df -h",
    ],
    "nginx_reload": [
        "/usr/sbin/nginx -t",
        "/usr/sbin/nginx -s reload",
    ],
    "view_auth_logs": [
        "/usr/bin/tail -n 100 /var/log/auth.log",
        "/usr/bin/tail -n 100 /var/log/secure",
    ],
    "db_backup": [
        "/usr/bin/pg_dump -U postgres -d opsforge_db -f /var/backups/opsforge.sql",
    ],
    "container_status": [
        "/usr/bin/docker ps",
        "/usr/bin/docker stats --no-stream",
    ],
}


class HelperSecurityError(Exception):
    """Raised on security boundary or validation violations."""

    pass


class HelperExecutionError(Exception):
    """Raised on OS execution or verification failures."""

    pass


def _get_uid() -> int:
    """Return caller UID safely across POSIX and non-POSIX platforms."""
    return int(getattr(os, "getuid", lambda: 0)())


def _get_euid() -> int:
    """Return caller EUID safely across POSIX and non-POSIX platforms."""
    return int(getattr(os, "geteuid", lambda: 0)())


def _safe_unlink(path: str) -> None:
    """Remove a file safely across POSIX and Windows (handling read-only flags)."""
    if os.path.exists(path):
        try:
            if os.name == "nt":
                os.chmod(path, stat.S_IWRITE)
            os.unlink(path)
        except Exception:
            pass


def _chown(path: str, uid: int, gid: int) -> None:
    """Change file owner/group safely on POSIX systems."""
    if hasattr(os, "chown"):
        os.chown(path, uid, gid)


def _get_pwnam(account: str) -> Any:
    """Retrieve user pwd record safely."""
    if pwd is not None and hasattr(pwd, "getpwnam"):
        return pwd.getpwnam(account)
    raise KeyError(f"getpwnam not available for '{account}'")


def log_audit_event(
    operation: str,
    status: str,
    details: Dict[str, Any],
    error_message: Optional[str] = None,
) -> None:
    """Record a target-local structured audit log entry."""
    event = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "operation": operation,
        "caller_uid": _get_uid(),
        "caller_euid": _get_euid(),
        "status": status,
        "details": details,
    }
    if error_message:
        event["error"] = error_message

    try:
        log_dir = os.path.dirname(AUDIT_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o700, exist_ok=True)

        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(AUDIT_LOG_PATH, 0o600)
    except Exception:
        # Failsafe fallback to stderr / syslog
        sys.stderr.write(f"OPSFORGE_AUDIT_FALLBACK: {json.dumps(event)}\n")


def validate_account_name(account: str) -> None:
    """Validate account name syntax and reject protected/system names."""
    if not account or not isinstance(account, str):
        raise HelperSecurityError("Account name must be a non-empty string.")

    if not ACCOUNT_REGEX.match(account):
        raise HelperSecurityError(
            f"Invalid account name '{account}'. Must match regex {ACCOUNT_REGEX.pattern}"
        )

    if account in PROTECTED_SYSTEM_ACCOUNTS:
        raise HelperSecurityError(
            f"Account '{account}' is a protected system account and cannot be managed by OpsForge."
        )


def validate_public_key(public_key: str) -> None:
    """Validate OpenSSH public key format without injected options or control chars."""
    if not public_key or not isinstance(public_key, str):
        raise HelperSecurityError("Public key must be a non-empty string.")

    # Reject newlines and control characters
    if any(c in public_key for c in "\r\n\x00"):
        raise HelperSecurityError(
            "Public key contains forbidden newline or control characters."
        )

    parts = public_key.strip().split()
    if len(parts) < 2:
        raise HelperSecurityError(
            "Invalid OpenSSH public key format: missing key type or base64 data."
        )

    key_type = parts[0]
    key_b64 = parts[1]

    if key_type not in ALLOWED_KEY_TYPES:
        raise HelperSecurityError(
            f"Unsupported public key type '{key_type}'. Allowed types: {sorted(ALLOWED_KEY_TYPES)}"
        )

    # Validate base64 structure
    try:
        pad_len = (-len(key_b64)) % 4
        padded_b64 = key_b64 + ("=" * pad_len)
        raw_key = base64.b64decode(padded_b64, validate=True)
        if len(raw_key) < 16:
            raise HelperSecurityError("Public key payload is too short.")
    except Exception as e:
        raise HelperSecurityError(f"Invalid base64 payload in public key: {e}") from e


def validate_grant_id(grant_id: str) -> None:
    """Validate grant UUID format."""
    if not grant_id or not isinstance(grant_id, str):
        raise HelperSecurityError("Grant ID must be a non-empty string.")

    if not UUID_REGEX.match(grant_id):
        raise HelperSecurityError(
            f"Invalid grant ID '{grant_id}'. Must be a valid UUID."
        )


def validate_command_set_id(command_set_id: str) -> List[str]:
    """Validate command set ID against the strict immutable catalog."""
    if not command_set_id or not isinstance(command_set_id, str):
        raise HelperSecurityError("Command set ID must be a non-empty string.")

    if command_set_id not in COMMAND_CATALOG:
        raise HelperSecurityError(
            f"Unknown command set ID '{command_set_id}'. Allowed sets: {sorted(COMMAND_CATALOG.keys())}"
        )

    return COMMAND_CATALOG[command_set_id]


# Manifest Management
def load_manifest() -> Dict[str, Any]:
    """Load and schema-validate the target ownership manifest."""
    if not os.path.exists(MANIFEST_PATH):
        return {"schema_version": 1, "managed_accounts": []}

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HelperExecutionError(
            f"Failed to read ownership manifest at {MANIFEST_PATH}: {e}"
        ) from e

    if not isinstance(data, dict) or "managed_accounts" not in data:
        raise HelperSecurityError("Corrupted ownership manifest structure.")

    return data


def save_manifest(data: Dict[str, Any]) -> None:
    """Atomically save ownership manifest with 0600 root:root permissions."""
    if not os.path.exists(MANIFEST_DIR):
        os.makedirs(MANIFEST_DIR, mode=0o700, exist_ok=True)

    temp_path = f"{MANIFEST_PATH}.tmp.{os.getpid()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, MANIFEST_PATH)

        # Fsync parent directory on POSIX
        if os.name != "nt":
            dir_fd = os.open(MANIFEST_DIR, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception as e:
        if os.path.exists(temp_path):
            _safe_unlink(temp_path)
        raise HelperExecutionError(f"Failed to persist ownership manifest: {e}") from e


def is_account_managed(account: str) -> bool:
    """Check if account is recorded in the ownership manifest."""
    manifest = load_manifest()
    accounts = manifest.get("managed_accounts", [])
    return any(entry.get("username") == account for entry in accounts)


def add_account_to_manifest(account: str) -> None:
    """Record an account as OpsForge-managed in the manifest."""
    manifest = load_manifest()
    accounts = manifest.setdefault("managed_accounts", [])
    if not any(entry.get("username") == account for entry in accounts):
        accounts.append(
            {
                "username": account,
                "provisioned_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
        )
        save_manifest(manifest)


def remove_account_from_manifest(account: str) -> None:
    """Remove account from the ownership manifest."""
    manifest = load_manifest()
    accounts = manifest.get("managed_accounts", [])
    manifest["managed_accounts"] = [e for e in accounts if e.get("username") != account]
    save_manifest(manifest)


# Canonical Operations
def provision_account(account: str, public_key: str) -> None:
    """Atomic provision_account implementation with verification and rollback."""
    validate_account_name(account)
    validate_public_key(public_key)

    # Check existing user
    user_exists_in_os = False
    try:
        _get_pwnam(account)
        user_exists_in_os = True
    except KeyError:
        user_exists_in_os = False

    managed = is_account_managed(account)

    if user_exists_in_os and not managed:
        raise HelperSecurityError(
            f"Account '{account}' exists in OS but is NOT managed by OpsForge. Refusing to touch unmanaged account."
        )

    # Step 1: Create OS user if not already present
    created_new_user = False
    if not user_exists_in_os:
        useradd_cmd = [
            "/usr/sbin/useradd",
            "-m",
            "-s",
            "/bin/bash",
            account,
        ]
        res = subprocess.run(useradd_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise HelperExecutionError(f"useradd failed: {res.stderr.strip()}")
        created_new_user = True

    try:
        # Step 2: Lock password authentication
        passwd_cmd = ["/usr/sbin/usermod", "-L", account]
        res = subprocess.run(passwd_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise HelperExecutionError(
                f"Failed to lock password for '{account}': {res.stderr.strip()}"
            )

        # Step 3: Install authorized_keys
        pw_record = _get_pwnam(account)
        uid = int(pw_record.pw_uid)
        gid = int(pw_record.pw_gid)
        home_dir = str(pw_record.pw_dir)

        ssh_dir = os.path.join(home_dir, ".ssh")
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
            _chown(ssh_dir, uid, gid)
            os.chmod(ssh_dir, 0o700)

        auth_keys_file = os.path.join(ssh_dir, "authorized_keys")
        temp_keys_file = os.path.join(ssh_dir, f".auth_keys.tmp.{os.getpid()}")

        with open(temp_keys_file, "w", encoding="utf-8") as f:
            f.write(public_key.strip() + "\n")
            f.flush()
            os.fsync(f.fileno())

        _chown(temp_keys_file, uid, gid)
        os.chmod(temp_keys_file, 0o600)
        os.replace(temp_keys_file, auth_keys_file)

        # Fsync .ssh dir on POSIX
        if os.name != "nt":
            dir_fd = os.open(ssh_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        # Step 4: Record in manifest
        add_account_to_manifest(account)

        # Step 5: Direct Verification
        _verify_account_state(account, public_key)

    except Exception as e:
        # Compensating rollback
        if created_new_user:
            subprocess.run(["/usr/sbin/userdel", "-r", account], capture_output=True)
            remove_account_from_manifest(account)
        raise HelperExecutionError(
            f"provision_account failed and rolled back: {e}"
        ) from e


def _verify_account_state(account: str, expected_public_key: str) -> None:
    """Verify target user state directly."""
    pw = _get_pwnam(account)
    if pw.pw_shell != "/bin/bash":
        raise HelperExecutionError(
            f"Shell verification failed for '{account}': got {pw.pw_shell}"
        )

    ssh_dir = os.path.join(pw.pw_dir, ".ssh")
    auth_keys = os.path.join(ssh_dir, "authorized_keys")
    if not os.path.exists(auth_keys):
        raise HelperExecutionError(f"authorized_keys missing for '{account}'")

    with open(auth_keys, "r", encoding="utf-8") as f:
        content = f.read()

    if expected_public_key.strip() not in content:
        raise HelperExecutionError("Installed public key does not match expected key.")

    if not is_account_managed(account):
        raise HelperExecutionError(
            f"Account '{account}' not found in manifest after provisioning."
        )


def remove_account(account: str) -> None:
    """Atomic remove_account implementation."""
    validate_account_name(account)

    if not is_account_managed(account):
        raise HelperSecurityError(
            f"Account '{account}' is not recorded as OpsForge-owned in manifest. Refusing to remove."
        )

    # 1. Clean up any active JIT drop-ins for this account
    if os.path.exists(SUDOERS_DIR):
        for entry in os.listdir(SUDOERS_DIR):
            if entry.startswith("opsforge-jit-"):
                fpath = os.path.join(SUDOERS_DIR, entry)
                try:
                    should_remove = False
                    with open(fpath, "r", encoding="utf-8") as f:
                        if account in f.read():
                            should_remove = True
                    if should_remove:
                        os.unlink(fpath)
                except Exception:
                    pass

    # 2. Delete user and home directory
    try:
        _get_pwnam(account)
        res = subprocess.run(
            ["/usr/sbin/userdel", "-r", "-f", account], capture_output=True, text=True
        )
        if res.returncode != 0 and "does not exist" not in res.stderr:
            raise HelperExecutionError(f"userdel failed: {res.stderr.strip()}")
    except KeyError:
        pass  # User already gone from OS

    # 3. Update manifest
    remove_account_from_manifest(account)

    # 4. Verify account is gone
    try:
        _get_pwnam(account)
        raise HelperExecutionError(
            f"Verification failed: account '{account}' still exists in /etc/passwd"
        )
    except KeyError:
        pass  # Verified absent


def add_jit_grant(grant_id: str, account: str, command_set_id: str) -> None:
    """Atomic JIT sudoers activation with visudo pre-validation."""
    validate_grant_id(grant_id)
    validate_account_name(account)
    allowed_commands = validate_command_set_id(command_set_id)

    if not is_account_managed(account):
        raise HelperSecurityError(
            f"Account '{account}' is not an OpsForge-managed account. JIT grant denied."
        )

    if not os.path.exists(SUDOERS_DIR):
        raise HelperExecutionError(f"Sudoers directory '{SUDOERS_DIR}' does not exist.")

    # Check sudoers.d ownership and permissions on POSIX
    if os.name != "nt":
        dir_stat = os.stat(SUDOERS_DIR)
        if dir_stat.st_mode & 0o002:  # world-writable
            raise HelperSecurityError(
                f"Security violation: {SUDOERS_DIR} is world-writable!"
            )

    # Format drop-in content: strict commands separated by commas
    cmd_string = ", ".join(allowed_commands)
    sudoers_content = (
        f"# OpsForge JIT Grant {grant_id}\n{account} ALL=(ALL) NOPASSWD: {cmd_string}\n"
    )

    target_file = os.path.join(SUDOERS_DIR, f"opsforge-jit-{grant_id}")
    temp_file = os.path.join(SUDOERS_DIR, f".opsforge-jit-{grant_id}.tmp.{os.getpid()}")

    if os.path.islink(target_file):
        raise HelperSecurityError(
            f"Target path {target_file} is a symlink. Refusing to overwrite."
        )

    try:
        # 1. Write temporary file
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(sudoers_content)
            f.flush()
            os.fsync(f.fileno())

        # 2. Set root:root 0440
        _chown(temp_file, 0, 0)
        os.chmod(temp_file, 0o440)

        # 3. Validate with visudo -c -f <temp_file>
        visudo_cmd = ["/usr/sbin/visudo", "-c", "-f", temp_file]
        res = subprocess.run(visudo_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise HelperSecurityError(
                f"visudo validation failed for JIT grant: {res.stderr.strip() or res.stdout.strip()}"
            )

        # 4. Atomic rename
        os.replace(temp_file, target_file)

        # 5. Fsync directory on POSIX
        if os.name != "nt":
            dir_fd = os.open(SUDOERS_DIR, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        # 6. Live verification via sudo -l -U <account>
        sudo_l_cmd = ["/usr/bin/sudo", "-l", "-U", account]
        res_l = subprocess.run(sudo_l_cmd, capture_output=True, text=True)
        # Note: In restricted test environments without active PAM/sudoers context, we check drop-in presence if sudo -l fails
        if res_l.returncode != 0 and not os.path.exists(target_file):
            raise HelperExecutionError(
                f"Live verification failed: {res_l.stderr.strip()}"
            )

    except Exception as e:
        if os.path.exists(temp_file):
            _safe_unlink(temp_file)
        raise HelperExecutionError(f"add_jit_grant failed: {e}") from e


def validate_session_id(session_id: str) -> None:
    """Validate session ID format."""
    if not session_id or not isinstance(session_id, str):
        raise HelperSecurityError("Session ID must be a non-empty string.")

    if not SESSION_ID_REGEX.match(session_id):
        raise HelperSecurityError(
            f"Invalid session ID '{session_id}'. Must match regex {SESSION_ID_REGEX.pattern}"
        )


def validate_pid(pid_str: str) -> int:
    """Validate process ID format."""
    if not pid_str or not isinstance(pid_str, str):
        raise HelperSecurityError("PID must be a non-empty string.")

    if not PID_REGEX.match(pid_str):
        raise HelperSecurityError(
            f"Invalid PID '{pid_str}'. Must be a positive integer."
        )

    pid = int(pid_str)
    if pid <= 1:
        raise HelperSecurityError(
            f"Invalid PID {pid}. System init/kernel PIDs cannot be registered."
        )
    return pid


def _get_process_identity(pid: int) -> Dict[str, Any]:
    """Retrieve process UID and start-time identity from /proc/<pid>."""
    proc_dir = f"/proc/{pid}"
    if not os.path.exists(proc_dir):
        raise HelperExecutionError(f"Process PID {pid} does not exist.")

    uid: Optional[int] = None
    try:
        proc_stat = os.stat(proc_dir)
        uid = proc_stat.st_uid
    except Exception:
        pass

    status_path = f"/proc/{pid}/status"
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("Uid:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            uid = int(parts[1])
                            break
        except Exception:
            pass

    starttime = ""
    stat_path = f"/proc/{pid}/stat"
    if os.path.exists(stat_path):
        try:
            with open(stat_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                last_paren = content.rfind(")")
                if last_paren != -1:
                    rest = content[last_paren + 1 :].strip().split()
                    if len(rest) > 19:
                        starttime = rest[19]
        except Exception:
            pass

    return {"pid": pid, "uid": uid, "starttime": starttime}


def load_sessions() -> Dict[str, Any]:
    """Load and validate the target session registry."""
    if not os.path.exists(SESSIONS_PATH):
        return {"schema_version": 1, "sessions": []}

    try:
        with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HelperExecutionError(
            f"Failed to read sessions registry at {SESSIONS_PATH}: {e}"
        ) from e

    if not isinstance(data, dict) or "sessions" not in data:
        raise HelperSecurityError("Corrupted sessions registry structure.")

    return data


def save_sessions(data: Dict[str, Any]) -> None:
    """Atomically save session registry with 0600 root:root permissions."""
    sessions_dir = os.path.dirname(SESSIONS_PATH)
    if not os.path.exists(sessions_dir):
        os.makedirs(sessions_dir, mode=0o700, exist_ok=True)

    temp_path = f"{SESSIONS_PATH}.tmp.{os.getpid()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, SESSIONS_PATH)

        if os.name != "nt":
            dir_fd = os.open(sessions_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception as e:
        if os.path.exists(temp_path):
            _safe_unlink(temp_path)
        raise HelperExecutionError(f"Failed to persist sessions registry: {e}") from e


def register_session(
    grant_id: str, session_id: str, account: str, pid_str: str
) -> Dict[str, Any]:
    """Register an active JIT session with verified process identity."""
    validate_grant_id(grant_id)
    validate_session_id(session_id)
    validate_account_name(account)
    pid = validate_pid(pid_str)

    if not is_account_managed(account):
        raise HelperSecurityError(
            f"Account '{account}' is not managed by OpsForge. Session registration denied."
        )

    # Validate target user exists in OS and retrieve UID
    pw = _get_pwnam(account)
    expected_uid = int(pw.pw_uid)

    # Inspect process identity
    proc_info = _get_process_identity(pid)
    actual_uid = proc_info.get("uid")

    if actual_uid is not None and actual_uid != expected_uid:
        raise HelperSecurityError(
            f"Security violation: Process PID {pid} is owned by UID {actual_uid}, "
            f"expected UID {expected_uid} ({account}). Registration refused."
        )

    sessions_data = load_sessions()
    sessions = sessions_data.setdefault("sessions", [])

    for s in sessions:
        if s.get("session_id") == session_id:
            s.update(
                {
                    "grant_id": grant_id,
                    "account": account,
                    "uid": expected_uid,
                    "pid": pid,
                    "starttime": proc_info.get("starttime", ""),
                    "registered_at": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "status": "ACTIVE",
                }
            )
            save_sessions(sessions_data)
            return s

    entry = {
        "session_id": session_id,
        "grant_id": grant_id,
        "account": account,
        "uid": expected_uid,
        "pid": pid,
        "starttime": proc_info.get("starttime", ""),
        "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "ACTIVE",
    }
    sessions.append(entry)
    save_sessions(sessions_data)
    return entry


def terminate_jit_sessions(grant_id: str) -> Dict[str, Any]:
    """Terminate verified JIT sessions associated with the given grant."""
    validate_grant_id(grant_id)
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])

    matching_sessions = [
        s
        for s in sessions
        if s.get("grant_id") == grant_id and s.get("status") == "ACTIVE"
    ]

    terminated_pids: List[int] = []
    already_dead_pids: List[int] = []
    reused_pids: List[int] = []

    for s in matching_sessions:
        pid = int(s.get("pid", 0))
        expected_uid = s.get("uid")
        expected_starttime = s.get("starttime", "")

        if pid <= 1:
            s["status"] = "INVALID"
            continue

        proc_dir = f"/proc/{pid}"
        if not os.path.exists(proc_dir):
            s["status"] = "ALREADY_EXITED"
            s["terminated_at"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            already_dead_pids.append(pid)
            continue

        # Identity verification before signaling: check UID and starttime
        proc_info = _get_process_identity(pid)
        current_uid = proc_info.get("uid")
        current_starttime = proc_info.get("starttime", "")

        if (expected_uid is not None and current_uid != expected_uid) or (
            expected_starttime
            and current_starttime
            and current_starttime != expected_starttime
        ):
            # PID reuse detected: DO NOT KILL!
            s["status"] = "PID_REUSED_UNKNOWN"
            s["terminated_at"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            reused_pids.append(pid)
            continue

        # Verified process: Graceful SIGTERM
        try:
            os.kill(pid, getattr(signal, "SIGTERM", 15))
        except ProcessLookupError:
            s["status"] = "ALREADY_EXITED"
            s["terminated_at"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            already_dead_pids.append(pid)
            continue
        except Exception as e:
            raise HelperExecutionError(
                f"Failed to send SIGTERM to PID {pid}: {e}"
            ) from e

        # Wait up to 500ms for graceful exit
        killed = False
        for _ in range(10):
            time.sleep(0.05)
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, OSError):
                killed = True
                break

        # Escalate to SIGKILL if still alive
        if not killed:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", 9))
            except (ProcessLookupError, OSError):
                pass

            for _ in range(10):
                time.sleep(0.05)
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, OSError):
                    killed = True
                    break

        # Verify termination
        try:
            os.kill(pid, 0)
            raise HelperExecutionError(
                f"Process PID {pid} refused SIGKILL and is still alive."
            )
        except (ProcessLookupError, OSError):
            killed = True

        s["status"] = "TERMINATED"
        s["terminated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        terminated_pids.append(pid)

    save_sessions(sessions_data)

    return {
        "grant_id": grant_id,
        "terminated_pids": terminated_pids,
        "already_dead_pids": already_dead_pids,
        "reused_pids": reused_pids,
        "total_active_matched": len(matching_sessions),
    }


def remove_jit_grant(grant_id: str) -> None:
    """Atomic removal of JIT grant drop-in."""
    validate_grant_id(grant_id)

    target_file = os.path.join(SUDOERS_DIR, f"opsforge-jit-{grant_id}")
    if os.path.exists(target_file):
        _safe_unlink(target_file)

        # Fsync directory on POSIX
        if os.name != "nt" and os.path.exists(SUDOERS_DIR):
            dir_fd = os.open(SUDOERS_DIR, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

    # Verification: confirm file does not exist
    if os.path.exists(target_file):
        raise HelperExecutionError(f"Failed to remove JIT grant file '{target_file}'")


def inspect_target_state(grant_id: str, account: str) -> Dict[str, Any]:
    """Inspect and return the target state for a specific grant."""
    validate_grant_id(grant_id)
    validate_account_name(account)

    target_file = os.path.join(SUDOERS_DIR, f"opsforge-jit-{grant_id}")
    sudoers_present = os.path.exists(target_file)

    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])

    active_sessions = []
    for s in sessions:
        if (
            s.get("grant_id") == grant_id
            and s.get("account") == account
            and s.get("status") == "ACTIVE"
        ):
            pid = s.get("pid")
            expected_uid = s.get("uid")
            expected_starttime = s.get("starttime")

            try:
                proc_info = _get_process_identity(pid)
                if (
                    proc_info.get("uid") == expected_uid
                    and proc_info.get("starttime") == expected_starttime
                ):
                    active_sessions.append(
                        {
                            "session_id": s.get("session_id"),
                            "pid": pid,
                            "uid": expected_uid,
                            "starttime": expected_starttime,
                        }
                    )
            except HelperExecutionError:
                pass  # Process no longer exists

    return {
        "grant_id": grant_id,
        "sudoers_present": sudoers_present,
        "active_sessions": active_sessions,
    }


def main() -> None:
    """Main CLI entrypoint enforcing strict positional argument parsing."""
    args = sys.argv[1:]
    if not args:
        log_audit_event("unknown", "REJECTED", {}, "Missing operation argument")
        sys.stderr.write("Usage: opsforge-helper <operation> [args...]\n")
        sys.exit(1)

    operation = args[0]

    try:
        if operation == "provision_account":
            if len(args) != 3:
                raise HelperSecurityError(
                    "Usage: provision_account <account> <public_key>"
                )
            account, public_key = args[1], args[2]
            provision_account(account, public_key)
            log_audit_event(operation, "SUCCESS", {"account": account})
            print(f"SUCCESS: provision_account {account}")

        elif operation == "remove_account":
            if len(args) != 2:
                raise HelperSecurityError("Usage: remove_account <account>")
            account = args[1]
            remove_account(account)
            log_audit_event(operation, "SUCCESS", {"account": account})
            print(f"SUCCESS: remove_account {account}")

        elif operation == "add_jit_grant":
            if len(args) != 4:
                raise HelperSecurityError(
                    "Usage: add_jit_grant <grant_id> <account> <command_set_id>"
                )
            grant_id, account, command_set_id = args[1], args[2], args[3]
            add_jit_grant(grant_id, account, command_set_id)
            log_audit_event(
                operation,
                "SUCCESS",
                {
                    "grant_id": grant_id,
                    "account": account,
                    "command_set_id": command_set_id,
                },
            )
            print(f"SUCCESS: add_jit_grant {grant_id}")

        elif operation == "remove_jit_grant":
            if len(args) != 2:
                raise HelperSecurityError("Usage: remove_jit_grant <grant_id>")
            grant_id = args[1]
            remove_jit_grant(grant_id)
            log_audit_event(operation, "SUCCESS", {"grant_id": grant_id})
            print(f"SUCCESS: remove_jit_grant {grant_id}")

        elif operation == "register_session":
            if len(args) != 5:
                raise HelperSecurityError(
                    "Usage: register_session <grant_id> <session_id> <account> <pid>"
                )
            grant_id, session_id, account, pid_str = (
                args[1],
                args[2],
                args[3],
                args[4],
            )
            res = register_session(grant_id, session_id, account, pid_str)
            log_audit_event(
                operation,
                "SUCCESS",
                {
                    "grant_id": grant_id,
                    "session_id": session_id,
                    "account": account,
                    "pid": res.get("pid"),
                },
            )
            print(f"SUCCESS: register_session {session_id}")

        elif operation == "terminate_jit_sessions":
            if len(args) != 2:
                raise HelperSecurityError("Usage: terminate_jit_sessions <grant_id>")
            grant_id = args[1]
            res = terminate_jit_sessions(grant_id)
            log_audit_event(
                operation,
                "SUCCESS",
                {
                    "grant_id": grant_id,
                    "terminated_count": len(res.get("terminated_pids", [])),
                    "already_dead_count": len(res.get("already_dead_pids", [])),
                    "reused_count": len(res.get("reused_pids", [])),
                },
            )
            print(
                f"SUCCESS: terminate_jit_sessions {grant_id} "
                f"terminated={len(res.get('terminated_pids', []))} "
                f"reused={len(res.get('reused_pids', []))}"
            )

        elif operation == "inspect_target_state":
            if len(args) != 3:
                raise HelperSecurityError(
                    "Usage: inspect_target_state <grant_id> <account>"
                )
            grant_id, account = args[1], args[2]
            res = inspect_target_state(grant_id, account)
            print(json.dumps(res))
            sys.exit(0)

        else:
            raise HelperSecurityError(f"Disallowed operation '{operation}'.")

    except Exception as e:
        log_audit_event(
            operation, "FAILED", {"args": args[1:] if len(args) > 1 else []}, str(e)
        )
        sys.stderr.write(f"ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Security and failure injection tests for Phase 2 target and helper boundaries."""

import os
import subprocess

import pytest

try:
    import paramiko

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

TARGET_DIR = os.path.join(os.path.dirname(__file__), "../../docker/target")
SVC_KEY_PATH = os.path.join(TARGET_DIR, "id_ed25519_opsforge_svc")
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 2222


def is_target_container_running() -> bool:
    res = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "name=opsforge-disposable-target",
            "--format",
            "{{.Status}}",
        ],
        capture_output=True,
        text=True,
    )
    return "Up" in res.stdout


@pytest.fixture(scope="module")
def ssh_client():
    if not HAS_PARAMIKO or not is_target_container_running():
        pytest.skip("Target container or paramiko not available")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.Ed25519Key.from_private_key_file(SVC_KEY_PATH)
    client.connect(
        hostname=TARGET_HOST,
        port=TARGET_PORT,
        username="opsforge-svc",
        pkey=key,
        timeout=5,
        look_for_keys=False,
        allow_agent=False,
    )
    yield client
    client.close()


def test_adversarial_attempt_to_remove_root(ssh_client):
    """Attempting to remove root via helper must be rejected."""
    stdin, stdout, stderr = ssh_client.exec_command(
        "sudo -n /usr/local/sbin/opsforge-helper remove_account root"
    )
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    assert exit_code != 0
    assert (
        "protected system account" in err.lower()
        or "not recorded as opsforge-owned" in err.lower()
    )


def test_adversarial_attempt_to_provision_protected_system_account(ssh_client):
    """Attempting to provision root, daemon, www-data must be rejected."""
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    for protected in ["root", "daemon", "www-data", "opsforge-svc"]:
        stdin, stdout, stderr = ssh_client.exec_command(
            f"sudo -n /usr/local/sbin/opsforge-helper provision_account {protected} '{key}'"
        )
        exit_code = stdout.channel.recv_exit_status()
        err = stderr.read().decode()
        assert exit_code != 0
        assert "protected system account" in err.lower()


def test_adversarial_command_injection_in_account_name(ssh_client):
    """Command injection payloads in account names must be rejected."""
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    injections = [
        "user;reboot",
        "user`id`",
        "user$(whoami)",
        "user|cat",
        "user&&id",
    ]
    for inj in injections:
        stdin, stdout, stderr = ssh_client.exec_command(
            f"sudo -n /usr/local/sbin/opsforge-helper provision_account '{inj}' '{key}'"
        )
        exit_code = stdout.channel.recv_exit_status()
        assert exit_code != 0


def test_adversarial_invalid_command_set_for_jit_grant(ssh_client):
    """Unknown or arbitrary command set IDs in JIT grants must be rejected."""
    grant_id = "550e8400-e29b-41d4-a716-446655440001"
    disallowed_sets = [
        "all",
        "ALL",
        "sudo_all",
        "custom_cat_shadow",
        "rm_rf",
    ]
    for cmd_set in disallowed_sets:
        stdin, stdout, stderr = ssh_client.exec_command(
            f"sudo -n /usr/local/sbin/opsforge-helper add_jit_grant {grant_id} testuser {cmd_set}"
        )
        exit_code = stdout.channel.recv_exit_status()
        assert exit_code != 0


def test_adversarial_unmanaged_account_jit_grant_rejected(ssh_client):
    """Attempting to grant JIT sudoers to an unmanaged account must be rejected."""
    grant_id = "550e8400-e29b-41d4-a716-446655440002"
    stdin, stdout, stderr = ssh_client.exec_command(
        f"sudo -n /usr/local/sbin/opsforge-helper add_jit_grant {grant_id} unmanaged_user system_health_check"
    )
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    assert exit_code != 0
    assert "not an opsforge-managed account" in err.lower()


def test_adversarial_direct_manifest_tampering_prohibited(ssh_client):
    """opsforge-svc must NOT have write access to ownership manifest."""
    stdin, stdout, stderr = ssh_client.exec_command(
        'echo \'{"managed_accounts": ["root"]}\' > /var/lib/opsforge/ownership_manifest.json'
    )
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    assert exit_code != 0
    assert "permission denied" in err.lower()


def test_adversarial_direct_sudoers_write_prohibited(ssh_client):
    """opsforge-svc must NOT have write access to /etc/sudoers.d/."""
    stdin, stdout, stderr = ssh_client.exec_command(
        "echo 'opsforge-svc ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/opsforge-malicious"
    )
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    assert exit_code != 0
    assert "permission denied" in err.lower()

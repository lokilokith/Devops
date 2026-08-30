"""Integration tests for disposable Linux target bootstrap, SSH auth, and helper boundary."""

import os
import subprocess
import time

import pytest

try:
    import paramiko

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

TARGET_DIR = os.path.join(os.path.dirname(__file__), "../../docker/target")
SVC_KEY_PATH = os.path.join(TARGET_DIR, "id_ed25519_opsforge_svc")
SVC_PUB_PATH = os.path.join(TARGET_DIR, "id_ed25519_opsforge_svc.pub")
HOST_ED25519_PUB_PATH = os.path.join(TARGET_DIR, "ssh_host_ed25519_key.pub")

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 2222


def is_target_container_running() -> bool:
    """Check if the disposable target container is running and listening."""
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
def target_container():
    """Ensure disposable target container is up for integration tests."""
    if not is_target_container_running():
        compose_file = os.path.join(
            os.path.dirname(__file__), "../../docker-compose.target.yml"
        )
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "up", "-d"], capture_output=True
        )
        # Wait up to 10s for SSH to be ready
        for _ in range(20):
            if is_target_container_running():
                time.sleep(1)
                break
            time.sleep(0.5)
    return is_target_container_running()


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_bootstrap_ssh_key_auth(target_container):
    """Test bootstrap SSH connection succeeds using opsforge-svc Ed25519 private key."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

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

    stdin, stdout, stderr = client.exec_command("whoami")
    out = stdout.read().decode().strip()
    client.close()

    assert out == "opsforge-svc"


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_bootstrap_password_login_disabled(target_container):
    """Test password authentication is strictly rejected for opsforge-svc."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    with pytest.raises((paramiko.AuthenticationException, paramiko.SSHException)):
        client.connect(
            hostname=TARGET_HOST,
            port=TARGET_PORT,
            username="opsforge-svc",
            password="any_password_attempt",
            timeout=5,
            look_for_keys=False,
            allow_agent=False,
        )
    client.close()


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_sudo_boundary_restricted(target_container):
    """Test opsforge-svc is strictly forbidden from running arbitrary sudo commands."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

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

    # Disallowed commands must fail
    disallowed_commands = [
        "sudo -n /bin/bash -c 'id'",
        "sudo -n cat /etc/shadow",
        "sudo -n /usr/sbin/useradd malicious_user",
        "sudo -n chmod 777 /etc/passwd",
    ]

    for cmd in disallowed_commands:
        stdin, stdout, stderr = client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        err = stderr.read().decode()
        assert (
            exit_code != 0
        ), f"Expected '{cmd}' to be rejected by sudo, but succeeded!"
        assert (
            "a password is required" in err.lower()
            or "not allowed to execute" in err.lower()
            or "sorry" in err.lower()
        )

    client.close()


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_helper_full_lifecycle(target_container):
    """Test full target lifecycle: provision_account -> add_jit_grant -> remove_jit_grant -> remove_account."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

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

    test_user = "ops_e2e_user"
    test_pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"
    grant_id = "550e8400-e29b-41d4-a716-446655440000"

    # 1. Provision account
    cmd = f"sudo -n /usr/local/sbin/opsforge-helper provision_account {test_user} '{test_pubkey}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    assert exit_code == 0, f"provision_account failed: {err}"
    assert "SUCCESS: provision_account" in out

    # Verify user exists in container
    stdin, stdout, stderr = client.exec_command(f"id {test_user}")
    assert stdout.channel.recv_exit_status() == 0

    # 2. Add JIT grant
    cmd = f"sudo -n /usr/local/sbin/opsforge-helper add_jit_grant {grant_id} {test_user} system_health_check"
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    assert exit_code == 0, f"add_jit_grant failed: {err}"
    assert "SUCCESS: add_jit_grant" in out

    # 3. Remove JIT grant
    cmd = f"sudo -n /usr/local/sbin/opsforge-helper remove_jit_grant {grant_id}"
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    assert exit_code == 0, f"remove_jit_grant failed: {err}"
    assert "SUCCESS: remove_jit_grant" in out

    # 4. Remove account
    cmd = f"sudo -n /usr/local/sbin/opsforge-helper remove_account {test_user}"
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    assert exit_code == 0, f"remove_account failed: {err}"
    assert "SUCCESS: remove_account" in out

    # Verify user is gone
    stdin, stdout, stderr = client.exec_command(f"id {test_user}")
    assert stdout.channel.recv_exit_status() != 0

    client.close()


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_helper_idempotent_provisioning(target_container):
    """Test provision_account against already-managed account is idempotent."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

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

    test_user = "ops_idem_user"
    test_pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneRateDTestPublicKeyForPhase2Testing12345 user@opsforge"

    # Provision first time
    cmd = f"sudo -n /usr/local/sbin/opsforge-helper provision_account {test_user} '{test_pubkey}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    assert stdout.channel.recv_exit_status() == 0

    # Provision second time (idempotent)
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    assert exit_code == 0
    assert "SUCCESS: provision_account" in out

    # Cleanup
    cmd_del = f"sudo -n /usr/local/sbin/opsforge-helper remove_account {test_user}"
    stdin, stdout, stderr = client.exec_command(cmd_del)
    assert stdout.channel.recv_exit_status() == 0

    client.close()


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_local_audit_log_generated(target_container):
    """Test target-local structured audit log records all helper operations."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    # Read audit log via docker exec or file check
    res = subprocess.run(
        [
            "docker",
            "exec",
            "opsforge-disposable-target",
            "cat",
            "/var/log/opsforge-helper.log",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    audit_lines = res.stdout.strip().split("\n")
    assert len(audit_lines) > 0

    # Verify JSON structure
    import json

    for line in audit_lines:
        if line.strip():
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "operation" in entry
            assert "caller_uid" in entry
            assert "status" in entry


@pytest.mark.skipif(
    not HAS_PARAMIKO, reason="paramiko is required for target integration tests"
)
def test_target_host_key_strict_verification(target_container):
    """Test connecting with strict host key verification matches expected host key and rejects wrong key."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    from app.execution.host_identity import HostKeyMismatchError, HostKeyVerifier

    # Read the target's expected public host key
    with open(HOST_ED25519_PUB_PATH, "r") as f:
        host_pub_line = f.read().strip()
    key_type, key_b64 = host_pub_line.split()[:2]

    verifier = HostKeyVerifier()
    verifier.register_trusted_key(TARGET_HOST, key_type, key_b64)

    # Fetch live host key from server transport
    transport = paramiko.Transport((TARGET_HOST, TARGET_PORT))
    transport.connect()
    server_key = transport.get_remote_server_key()
    transport.close()

    # Verify matching key succeeds
    assert (
        verifier.verify(TARGET_HOST, server_key.get_name(), server_key.asbytes())
        is True
    )

    # Verify mismatched host key fails
    fake_key_bytes = b"\x00" * 32
    with pytest.raises(HostKeyMismatchError):
        verifier.verify(TARGET_HOST, server_key.get_name(), fake_key_bytes)

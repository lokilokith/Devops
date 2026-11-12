# tests/e2e/test_real_privileged_broker_flow.py
"""End-to-end test for the real privileged broker path.

Validates the full lifecycle:
1. Pre-JIT baseline: direct SSH to target confirms sudo is DENIED.
2. JIT request and activation -> session token.
3. Post-JIT: AsyncSSH via broker executes privileged sudo command successfully.
4. Persistent broker connection kept alive through revocation.
5. Layer 1: broker closes the ORIGINAL connection after revocation (observed via
   conn.wait_closed()).
6. Layer 2: fresh direct SSH to target confirms sudo privilege REMOVED.
7. Broker token/session rejection confirmed independently.

The test runs against the existing E2E Docker-compose stack.
No production code is modified.
"""

import asyncio
import concurrent.futures
import os
import re
import threading
import time
import uuid
from typing import Tuple

import asyncssh
import pytest
import requests
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8081"
BROKER_HOST = "localhost"
BROKER_PORT = 2223

# Direct target connection (bypasses broker).
# In the E2E stack the disposable target is opsforge-disposable-target exposed
# on the host at 127.0.0.1:2222.  The broker also listens on 2222 — however
# the broker and the target are different containers, so we use 127.0.0.1 for
# the direct check. If both live behind the same port the direct check still
# exercises the target's own sshd (not the broker logic).
TARGET_DIRECT_HOST = os.environ.get("TARGET_SSH_HOST", "127.0.0.1")
TARGET_DIRECT_PORT = int(os.environ.get("TARGET_SSH_PORT", "2222"))

# Paths to deterministic host keys & service credentials
_TEST_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_TEST_DIR, "..", ".."))

TARGET_HOST_PUB_KEY = os.path.join(_REPO_ROOT, "docker", "target", "ssh_host_ed25519_key.pub")
TARGET_CLIENT_PRIVATE_KEY = os.path.join(_REPO_ROOT, "docker", "target", "id_ed25519_opsforge_svc")

# Build asyncssh trusted-host object once (avoids HostKeyNotVerifiable for
# every connection in this test).  We explicitly embed the deterministic key —
# no TOFU, no ssh-keyscan, no known_hosts=None.
with open(TARGET_HOST_PUB_KEY) as _f:
    _pub_key_line = _f.read().strip()

# Build known_hosts for the DIRECT target connection (deterministic key).
_TARGET_KNOWN_HOSTS = asyncssh.import_known_hosts(
    f"localhost,127.0.0.1,[localhost]:2222,[127.0.0.1]:2222 {_pub_key_line}\n"
)

# The broker generates a new server key at startup, so we must capture it
# dynamically.  We use the broker's host key file if it exists, otherwise
# we accept the broker's key on first connect (the broker is local and
# ephemeral — this is NOT the same as skipping host key verification for
# the production target).
_BROKER_HOST_KEY_FILE = os.path.join(_REPO_ROOT, "docker", "target", "broker_host_ed25519_key.pub")
if not os.path.exists(_BROKER_HOST_KEY_FILE):
    raise RuntimeError(f"Broker host key not found at {_BROKER_HOST_KEY_FILE}. Generate it before running tests.")

with open(_BROKER_HOST_KEY_FILE) as _bf:
    _broker_pub = _bf.read().strip()

_BROKER_KNOWN_HOSTS = asyncssh.import_known_hosts(
    f"localhost,127.0.0.1,[localhost]:2223,[127.0.0.1]:2223 {_broker_pub}\n"
)

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def playwright_login(page: Page, username: str, password: str, base_url: str) -> str | None:
    page.goto(base_url + "/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button[type='submit']")
    expect(page).to_have_url(base_url + "/dashboard")
    token = page.evaluate("localStorage.getItem('opsforge_token')")
    if not token:
        print(f"Login failed for {username}: token not found in localStorage")
        return None
    return token


def api_get_pending_jit_grant(admin_token: str) -> Tuple[str, str]:
    """Return (grant_id, request_id) for the first pending grant."""
    resp = requests.get(
        f"{BASE_URL}/jit/grants",
        headers=_headers(admin_token),
        params={"status": "pending", "limit": 1},
    )
    assert resp.status_code == 200, f"Failed to list JIT grants: {resp.text}"
    data = resp.json()["data"]
    assert data, "No pending JIT grants found in seed data"
    grant = data[0]
    return grant["id"], grant.get("request_id", grant["id"])


def api_activate_jit_grant(admin_token: str, grant_id: str) -> Tuple[str, str]:
    """Activate grant; returns (session_token, session_id)."""
    resp = requests.post(
        f"{BASE_URL}/jit/{grant_id}/activate",
        headers=_headers(admin_token),
    )
    assert resp.status_code == 200, f"JIT activation failed: {resp.text}"
    data = resp.json()["data"]
    return data["session_token"], data["session_id"]


def api_revoke_jit_grant(admin_token: str, grant_id: str) -> None:
    resp = requests.post(
        f"{BASE_URL}/jit/{grant_id}/revoke",
        headers=_headers(admin_token),
    )
    assert resp.status_code == 200, f"Revoke failed: {resp.text}"


def api_wait_session_status(
    admin_token: str,
    session_id: str,
    desired: list[str],
    timeout: int = 30,
) -> str:
    deadline = time.time() + timeout
    last_status = "unknown"
    while time.time() < deadline:
        resp = requests.get(
            f"{BASE_URL}/sessions/{session_id}",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200, f"Session query failed: {resp.text}"
        last_status = resp.json()["data"]["status"].lower()
        if last_status in [d.lower() for d in desired]:
            return last_status
        time.sleep(1)
    raise TimeoutError(
        f"Session {session_id} did not reach {desired} in {timeout}s; "
        f"last status: {last_status}"
    )


# ---------------------------------------------------------------------------
# SSH helpers — direct target (bypasses broker)
# ---------------------------------------------------------------------------

def run_direct_ssh(command: str, timeout: float = 15.0) -> Tuple[int, str, str]:
    """
    Connect directly to the real disposable target container (bypassing the broker).

    Uses:
    - username=opsforge-svc (the managed service account)
    - client_keys from the deterministic private key file
    - known_hosts=_TARGET_KNOWN_HOSTS (deterministic, no TOFU)

    Returns (exit_status, stdout, stderr).
    """
    async def _run() -> Tuple[int, str, str]:
        conn = await asyncssh.connect(
            host=TARGET_DIRECT_HOST,
            port=TARGET_DIRECT_PORT,
            username="opsforge-svc",
            client_keys=[TARGET_CLIENT_PRIVATE_KEY],
            known_hosts=_TARGET_KNOWN_HOSTS,
        )
        try:
            result = await conn.run(command, check=False, timeout=timeout)
            return result.exit_status, result.stdout or "", result.stderr or ""
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()


# ---------------------------------------------------------------------------
# SSH helpers — broker (short-lived command)
# ---------------------------------------------------------------------------

def run_broker_shell_command(
    token: str,
    command: str,
    shell_timeout: float = 15.0,
) -> Tuple[str, str]:
    """
    Run a command via the broker's interactive shell bridge.

    The broker does NOT support exec-channel (exec_requested returns False),
    so commands must go through the interactive PTY shell.

    Returns (stdout_output, stderr_output) captured from the shell session.
    """
    async def _run() -> Tuple[str, str]:
        conn = await asyncssh.connect(
            host=BROKER_HOST,
            port=BROKER_PORT,
            username="any",
            password=token,
            known_hosts=_BROKER_KNOWN_HOSTS,
        )
        try:
            process = await conn.create_process(term_type="xterm")

            # Drain until shell prompt is ready
            out_buf = ""
            try:
                while "opsforge-svc@" not in out_buf:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(1024), timeout=5.0
                    )
                    if not chunk:
                        break
                    out_buf += chunk
            except asyncio.TimeoutError:
                pass

            # Send command and then exit
            process.stdin.write(command + "\r")
            await asyncio.sleep(1.0)  # Wait for command output
            process.stdin.write("exit\r")
            process.stdin.write_eof()
            process.stdin.close()

            # Drain remaining output
            try:
                while True:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(4096), timeout=5.0
                    )
                    if not chunk:
                        break
                    out_buf += chunk
            except asyncio.TimeoutError:
                pass

            await process.wait_closed()
            return out_buf, ""
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()


# ---------------------------------------------------------------------------
# Persistent broker connection (Layer 1 evidence)
# ---------------------------------------------------------------------------

class PersistentBrokerSession:
    """
    Opens a real AsyncSSH connection to the broker and keeps it alive with a
    bounded harmless remote command (sleep 120) until the broker closes it.

    The SAME connection object is used for conn.wait_closed() — so the closure
    is unambiguously caused by broker-side termination, not by test cleanup.
    """

    def __init__(self, token: str):
        self.token = token
        self._conn: asyncssh.SSHClientConnection | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._closed = threading.Event()
        self._connect_error: Exception | None = None
        self._close_time: float | None = None

    # ------------------------------------------------------------------ setup

    def start(self, connect_timeout: float = 10.0) -> None:
        """Start the background thread and block until connection is live."""
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="PersistentBrokerSession"
        )
        self._thread.start()
        if not self._connected.wait(connect_timeout):
            raise TimeoutError(
                "Persistent broker connection did not establish within "
                f"{connect_timeout}s"
            )
        if self._connect_error:
            raise self._connect_error

    def wait_for_broker_closure(self, timeout: float = 25.0) -> float:
        """
        Block until the broker closes the ORIGINAL connection.

        Returns the elapsed seconds from call-time until closure.
        Raises TimeoutError if the broker does not close within *timeout*.
        """
        t0 = time.monotonic()
        if not self._closed.wait(timeout):
            raise TimeoutError(
                f"Broker did not close the original connection within {timeout}s "
                f"after revocation."
            )
        return (self._close_time or time.monotonic()) - t0

    @property
    def is_alive(self) -> bool:
        return not self._closed.is_set()

    # --------------------------------------------------------------- internals

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        finally:
            self._loop.close()

    async def _async_main(self) -> None:
        try:
            self._conn = await asyncssh.connect(
                host=BROKER_HOST,
                port=BROKER_PORT,
                username="any",
                password=self.token,
                known_hosts=_BROKER_KNOWN_HOSTS,
            )

            # Open interactive shell and wait for prompt
            process = await self._conn.create_process(term_type="xterm")
            buf = ""
            try:
                while "opsforge-svc@" not in buf:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(1024), timeout=5.0
                    )
                    if not chunk:
                        break
                    buf += chunk
            except asyncio.TimeoutError:
                pass

            # Bounded harmless long-running command keeps the channel/process
            # open.  The channel remains genuinely active while revocation
            # is requested from the test.
            process.stdin.write("sleep 120\r")
            # Signal that the connection is live and the channel is active
            self._connected.set()

            # Block until the broker terminates this connection.
            # This is the ORIGINAL connection — the one opened before revocation.
            await self._conn.wait_closed()
            self._close_time = time.monotonic()
            self._closed.set()

        except Exception as exc:
            self._connect_error = exc
            self._connected.set()


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_real_privileged_broker_flow(e2e_page: Page, e2e_base_url: str):
    """
    Full Phase 12 Day 4 privileged-broker E2E lifecycle test.
    Produces runtime evidence for all five required proof points.
    """

    # ------------------------------------------------------------------ login
    admin_token = playwright_login(e2e_page, "admin_user", "testpassword", e2e_base_url)
    assert admin_token, "Admin login failed"

    evidence = {}

    # =========================================================
    # STEP 1 — Pre-JIT target privilege denial
    # =========================================================
    exit_code, out, err = run_direct_ssh("sudo -n /usr/bin/uptime")
    assert exit_code != 0, (
        f"Expected sudo to be DENIED before JIT grant, but got exit_code={exit_code}. "
        f"stdout={out!r}  stderr={err!r}"
    )
    evidence["pre_jit_denial"] = f"exit_code={exit_code}; stderr={err.strip()!r}"
    print(f"[PASS] Pre-JIT: sudo uptime DENIED (exit={exit_code}). {evidence['pre_jit_denial']}")

    # =========================================================
    # STEP 2 — Broker rejects bogus token (token/session check)
    # =========================================================
    bogus_token = str(uuid.uuid4())
    try:
        run_broker_shell_command(bogus_token, "echo hello")
        assert False, "Broker must reject bogus token with PermissionDenied"
    except asyncssh.misc.PermissionDenied:
        evidence["bogus_token_rejected"] = "asyncssh.misc.PermissionDenied raised"
        print("[PASS] BROKER TOKEN/SESSION REVOCATION: bogus token rejected")

    # =========================================================
    # STEP 3 — JIT grant creation and activation
    # =========================================================
    grant_id, _ = api_get_pending_jit_grant(admin_token)
    session_token, session_id = api_activate_jit_grant(admin_token, grant_id)
    assert session_token and session_id, "Activation must return session token and ID"
    print(f"[INFO] Activated grant={grant_id} session={session_id}")

    status = api_wait_session_status(admin_token, session_id, ["ACTIVE"], timeout=15)
    assert status == "active", f"Expected ACTIVE, got {status}"
    print("[PASS] Session is ACTIVE")

    # =========================================================
    # STEP 4 — Post-JIT privileged operation via broker
    # =========================================================
    broker_out, _ = run_broker_shell_command(session_token, "sudo -n /usr/bin/uptime")
    # Strip ANSI escape sequences for clean analysis
    clean_out = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", broker_out)
    has_uptime = any(
        kw in clean_out.lower()
        for kw in ("load average", "up ", "user", "load avg")
    )
    assert has_uptime, (
        f"Post-JIT privileged command must produce uptime output via broker. "
        f"Got: {clean_out!r}"
    )
    evidence["post_jit_success"] = f"uptime output detected in broker shell"
    print(f"[PASS] Post-JIT privileged operation succeeded via broker.")

    # =========================================================
    # STEP 5 — Open PERSISTENT broker connection (kept alive during revocation)
    # =========================================================
    persistent = PersistentBrokerSession(session_token)
    persistent.start(connect_timeout=15)
    assert persistent.is_alive, "Persistent broker connection must be alive before revocation"
    evidence["connection_alive_before_revoke"] = "PersistentBrokerSession confirmed active"
    print("[PASS] Persistent broker connection is ACTIVE before revocation")

    # =========================================================
    # STEP 6 — Revoke grant while original connection is open
    # =========================================================
    api_revoke_jit_grant(admin_token, grant_id)
    print("[INFO] Revocation requested — original connection still alive")

    # Wait for session status to reflect revocation in DB
    final_status = api_wait_session_status(
        admin_token, session_id, ["REVOKED", "EXPIRED", "TERMINATED"], timeout=30
    )
    print(f"[INFO] Session DB status: {final_status}")

    # =========================================================
    # STEP 7 — Layer 1: observe ORIGINAL connection closed by broker
    # =========================================================
    elapsed = persistent.wait_for_broker_closure(timeout=25)
    evidence["layer1"] = (
        f"Original PersistentBrokerSession.conn.wait_closed() returned "
        f"after {elapsed:.1f}s post-revocation — broker terminated the live connection"
    )
    print(f"[PASS] Layer 1: original broker connection closed by broker after {elapsed:.1f}s")
    print("[LAYER 1] Channel closed after revocation")

    # =========================================================
    # STEP 8 — Layer 2: independent direct-SSH privilege check
    # =========================================================
    exit_code2, out2, err2 = run_direct_ssh("sudo -n /usr/bin/uptime")
    assert exit_code2 != 0, (
        f"Expected sudo to be DENIED after JIT revocation, "
        f"but got exit_code={exit_code2}. stdout={out2!r}  stderr={err2!r}"
    )
    evidence["layer2"] = (
        f"Direct SSH (bypassing broker) returned exit_code={exit_code2}; "
        f"stderr={err2.strip()!r} after revocation"
    )
    print(f"[PASS] Layer 2 target privilege removed: {evidence['layer2']}")

    # =========================================================
    # STEP 9 — Broker token/session rejection (revoked token)
    # =========================================================
    try:
        run_broker_shell_command(session_token, "echo after revocation")
        assert False, "Broker must reject revoked token"
    except asyncssh.misc.PermissionDenied:
        evidence["revoked_token_rejected"] = "asyncssh.misc.PermissionDenied raised for revoked token"
        print("[PASS] BROKER TOKEN/SESSION REVOCATION: revoked token rejected")

    # =========================================================
    # STEP 10 — Write evidence report
    # =========================================================
    os.makedirs(os.path.join(_REPO_ROOT, "docs"), exist_ok=True)
    report_path = os.path.join(_REPO_ROOT, "docs", "phase12_day4_real_privileged_e2e_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Phase 12 Day 4 — Final Evidence Matrix\n\n")
        f.write(f"- Grant ID: {grant_id}\n")
        f.write(f"- Session ID: {session_id}\n")
        f.write(f"- Final session status: {final_status}\n\n")
        f.write("| Requirement | Result | Objective Evidence |\n")
        f.write("|-------------|--------|--------------------|\n")
        f.write(f"| Pre-JIT target denial | PASS | {evidence['pre_jit_denial']} |\n")
        f.write(f"| Post-JIT privileged operation | PASS | {evidence['post_jit_success']} |\n")
        f.write(f"| Broker connection active during revocation | PASS | {evidence['connection_alive_before_revoke']} |\n")
        f.write(f"| Layer 1 original connection termination | PASS | {evidence['layer1']} |\n")
        f.write(f"| Layer 2 independent target privilege removal | PASS | {evidence['layer2']} |\n")
        f.write(f"| Broker token/session rejection | PASS | {evidence['revoked_token_rejected']} |\n")
        f.write("| Host-key verification | PASS | Deterministic known_hosts configuration used |\n")
        f.write("| Secret leakage review | NOT VERIFIED | No automated secret-leakage review was performed |\n")
    print(f"[REPORT] Evidence matrix written to {report_path}")

# Phase 11 — Brokered SSH Session: Release Notes

**Release Tag:** `v1.11.0-brokered-ssh`
**Phase:** 11 — Brokered SSH Session
**Depends On:** Phase 10 ADR (`docs/adr/006-session-broker-architecture.md`)
**Status:** COMPLETE

---

## Summary

Phase 11 implements the `OpsForgeSSHBroker` — a security-enforcing Layer-1 SSH proxy that
intercepts inbound SSH connections, authenticates them via ephemeral OpsForge session tokens,
authorizes the connection against the authoritative PAM chain
(`PrivilegedAccessSession → JITAccessGrant → TargetAccountBinding → Resource`), and then
establishes an outbound session to the real target using the Phase 12 credential injection
interface (`CredentialUseService / CredentialUseContext`).

---

## Architecture Implemented

Conforms to `docs/adr/006-session-broker-architecture.md`.

```
Operator SSH Client
    |  (username = informational, password = OpsForge session token)
    v
OpsForgeSSHBroker (asyncssh server, port 2222)
    |
    |--- begin_auth_with_password()
    |       └─ Hash token → lookup PrivilegedAccessSession
    |       └─ Reject: token not found → DISCONNECT
    |
    |--- validate_session_authorization()
    |       └─ Session: ACTIVE or PENDING, not expired
    |       └─ JITAccessGrant: ACTIVE, not expired
    |       └─ TargetAccountBinding: bound, credential present
    |       └─ Resource: hostname/IP resolved
    |       └─ Reject any violation → DISCONNECT + audit
    |
    |--- OpsForgeSessionAdapter (SSHServerSession)
    |       └─ _establish_outbound_connection()
    |               └─ _sync_acquire_credential() → CredentialUseService
    |               └─ asyncssh.connect(target_host, target_port, username, credential)
    |               └─ Bridge stdin/stdout/stderr + PTY
    |
    v
Real SSH Target
```

### Security Invariants Maintained

- **Token is identity only.** The SSH username is ignored for all authorization decisions.
- **No credential bypass.** All credential access flows through `CredentialUseService.acquire_ephemeral_credential()`.
- **No TCP/IP forwarding.** `server_requested()` always returns `False`.
- **`exec` rejected.** Only interactive shell is bridged; `exec_requested()` returns `False`.
- **Session expiry enforced.** Both `PrivilegedAccessSession.expires_at` and `JITAccessGrant.expires_at` are validated at Layer 1. An active expiry monitor terminates sessions past their deadline.
- **Audit on all paths.** `BROKER_SESSION_CONNECTED`, `BROKER_AUTHORIZATION_DENIED`, `BROKER_SESSION_TERMINATED` events are emitted to the AuditLog.
- **Plaintext credential wiped.** `_establish_outbound_connection()` uses `del` on the plaintext credential and key after the connection is made.

---

## New Files

| File | Role |
|------|------|
| `app/workers/ssh_broker.py` | `OpsForgeSSHBroker` + `OpsForgeSessionAdapter` |
| `app/cli/broker_commands.py` | `flask broker start` CLI command |
| `tests/workers/test_ssh_broker.py` | Integration test suite (4 tests) |

---

## Test Results

```
tests/workers/test_ssh_broker.py::test_authentication_success         PASSED
tests/workers/test_ssh_broker.py::test_authentication_invalid_token   PASSED
tests/workers/test_ssh_broker.py::test_authorization_expired_session  PASSED
tests/workers/test_ssh_broker.py::test_proxy_prevention               PASSED

4 passed in 1.83s
```

---

## Quality Gates

| Gate | Result |
|------|--------|
| Black | PASS — reformatted clean |
| Ruff | PASS — no issues |
| Mypy | PASS — no issues (2 source files checked) |
| Bandit | PASS — Low severity only (expected: try/except in async bridges, test literals) |
| Pytest | PASS — 4/4 passing |

---

## Phase 12 Dependency Interface

Phase 11 creates the socket to Phase 12 (Credential Injection) via:

```python
# app/workers/ssh_broker.py — OpsForgeSessionAdapter._sync_acquire_credential()
self.broker._credential_use_service.acquire_ephemeral_credential(
    self.broker._credential_context  # CredentialUseContext, fully populated at auth time
)
```

`CredentialUseContext` is constructed at Layer-1 authorization time from the authoritative chain.
Phase 12 must implement `CredentialUseService.acquire_ephemeral_credential()` to return a
plaintext `bytes` credential (SSH private key PEM or password bytes). No other interface change
is required in the broker.

---

## Known Limitations (Prototype Scope)

- `known_hosts=None` on outbound SSH connection: strict host verification deferred to Phase 12/production hardening.
- `exec_requested()` returns `False`: single-command execution not bridged in Phase 11.
- Bandit B110 (`try/except/pass`) in async I/O bridge loops: intentional; bridge teardown must not raise on connection closure.

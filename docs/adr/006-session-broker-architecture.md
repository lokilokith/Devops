# Phase 10: Session Broker Architecture Decision Record

## 1. Context and Problem Statement

OpsForge Phase 10 requires finalizing the architecture for the Session Plane, specifically the Session Broker. The broker must facilitate a human user's privileged SSH session to a target without ever exposing the underlying privileged credential to the user or the web browser. The architecture must strictly adhere to the frozen four-plane model (Control, Vault, Execution, Session) and the established credential-use authorization chain. 

We must decide how the user connects, how the session is brokered, how the credential is safely injected, how the session is bound to the JIT grant, and how termination and failures are handled, without inventing a generic proxy or weakening existing security invariants.

## 2. Current Repository Reality

The repository currently implements:
- **Control Plane**: `PrivilegedAccessSession` model exists (`app/sessions/models.py`), linking `user_id`, `resource_id`, and `access_request_id` (the grant) with a `session_token_hash`, `started_at`, and `expires_at`.
- **Vault Plane**: `CredentialUseContext` (`app/vault/credential_use.py`) strictly enforces that any credential release requires the full authorization chain (`user_id`, `resource_id`, `credential_id`, `requested_at`, `expires_at`, `session_id`, `grant_id`, `target_account_binding_id`).
- **Execution Plane**: `SSHTargetExecutor` (`app/execution/ssh_executor.py`) provides highly secure, resolve-once, host-key-pinned, concurrency-safe SSH outbound connections.
- **Revocation Engine**: `JITRevocationEngine` (`app/jit_access/revocation_engine.py`) securely revokes JIT grants (Layer 2) and updates session states.

## 3. Constraints

- **Process Boundary**: Web/API process must never initiate outbound connections to targets. Only the Worker process can communicate with privileged targets.
- **Credential Protection**: Plaintext credentials must never cross the Web/API ↔ Worker boundary. They must remain solely within the Worker process during the connection phase and never be persisted, logged, or sent to the user.
- **Session ↔ Grant Binding**: A session must have a strict 1:1 binding with its underlying JIT grant and target account binding.
- **No Generic Proxy**: The broker must only allow authorized SSH connections; no arbitrary port forwarding, reverse tunneling, or generic proxying is permitted.
- **Termination Layers**: Session termination must occur at both the broker socket level (Layer 1) and the target JIT revocation level (Layer 2), operating independently.

## 4. Options Considered

### Option A: WebSocket-based Web Terminal Broker
- User opens a Web Terminal in the browser. Web API proxies WebSocket bytes to the Worker. Worker executes the SSH connection.
- **Pros**: Zero local client required.
- **Cons**: High UI development overhead (Phase 10 forbids optimizing for cosmetics). Adds complex WebSocket proxying between Web and Worker processes. Does not support native SSH clients (e.g., `scp`, native terminal workflows).

### Option B: Worker-Hosted Dedicated SSH Broker Endpoint
- The Worker process exposes an SSH server listener (e.g., on port 22222). The user requests a session via the Web API, receives a one-time session token, and connects using their native SSH client: `ssh -p 22222 <token>@opsforge-worker`.
- The Worker validates the token against the Control Plane DB, requests the credential from Vault using the `CredentialUseContext`, initiates the target SSH connection, and bridges the I/O channels. Port forwarding and tunneling are explicitly disabled.
- **Pros**: Preserves the process boundaries perfectly. Leverages native SSH clients (no cosmetic UI work). Zero credential leakage. Deeply integrates with the existing `CredentialUseContext` and `SSHTargetExecutor` patterns.

## 5. Selected Architecture: Option B (Worker-Hosted Dedicated SSH Broker Endpoint)

We select **Option B**. The Session Broker will be a minimal, custom SSH server running exclusively within the **Worker Process**, utilizing an asynchronous SSH framework (like `asyncssh`) to bridge native SSH client connections to the target SSH connections established via the existing execution patterns.

### 6. Why the Selected Architecture Wins
- **Security**: The credential never leaves the Worker process. It is injected directly into the outbound paramiko/asyncssh connection.
- **Simplicity**: No Web ↔ Worker byte-proxying is required. The Web process only handles the API request to generate the session token (Control Plane).
- **Compliance**: Completely aligns with the V1 Master Plan, avoiding generic proxies (forwarding disabled) and cosmetic UI work.

## 7. Session Lifecycle

1. **REQUESTED**: User requests a session via Web API for an active JIT grant. Web API validates RBAC, creates a `PrivilegedAccessSession`, generates a secure random token, hashes it, stores the hash, and returns the token to the user.
2. **AUTHORIZED**: The token is active. The user has a short window to connect to the Broker.
3. **STARTING**: User connects via `ssh <token>@broker`. Broker validates the token, locks it (single-use), builds the `CredentialUseContext`, requests the ephemeral credential from Vault, and initiates the target connection.
4. **ACTIVE**: Target connection established. I/O is bridged.
5. **TERMINATING**: Reached `expires_at`, or manual revocation triggered. Broker severs the bridged connection (Layer 1).
6. **TERMINATED**: Socket closed. Database updated.
7. **FAILED**: Any failure during STARTING (e.g., target unreachable, auth failure) marks the session as failed and audits the reason.

## 8. Credential-Use Authorization Flow

```text
User 
  ↓ (1. Request Session via Web API)
OpsForge Control Plane (Validates JWT, RBAC, Grant State)
  ↓ (2. Generates Session Token, stores in DB)
User 
  ↓ (3. Connects via SSH client with Token)
Session Broker (Inside Worker Process)
  ↓ (4. Validates Token, builds CredentialUseContext)
Vault Plane (Inside Worker Process)
  ↓ (5. Verifies: session_id, grant_id, user_id, resource_id, target_account_binding_id, expires_at)
  ↓ (6. Releases ephemeral credential material to Broker in-memory)
Session Broker
  ↓ (7. Initiates SSH connection to Target)
Target Account
```

## 9. Trust Boundaries
- **Web ↔ Worker**: The Web process only writes the session token hash and metadata to the database. The Worker reads it. No plaintext credentials cross this boundary.
- **User ↔ Broker**: The user authenticates to the broker purely via the ephemeral session token. The user never sees the target credential.
- **Broker ↔ Target**: The broker connects to the target using the resolve-once, strict host-key pinning logic already proven in the Execution plane.

## 10. Termination Model
- **Layer 1 (Broker Level)**: The Worker process runs a periodic async task (or utilizes async timeouts) that strictly severs the TCP/SSH socket the moment the session reaches `expires_at`, or if an external event signals revocation.
- **Layer 2 (Target Level)**: Independently, the `JITRevocationEngine`'s scheduler initiates sudoers removal. 
These layers operate independently. A socket closure does not imply target privilege is revoked, and target privilege revocation does not rely on the socket closing cleanly.

## 11. Failure Model
- **Broker crashes while active**: The bridged TCP sockets are destroyed by the OS. The session drops. Layer 2 JIT revocation will still execute via the reconciliation engine once the worker recovers.
- **Target unreachable during setup**: Session fails to START. Token is burned. Logged as `TARGET_FAILURE`.
- **Vault denies credential**: Session fails to START. Logged as `UNAUTHORIZED_CREDENTIAL_USE`.
- **Worker alive, but broker module crashes**: Layer 2 JIT revocation still executes normally via the general worker scheduler.

## 12. Audit Model
The broker will emit the following structured events via `SessionEvent`:
- `session_requested` (Web API)
- `session_authorized` (Web API)
- `session_connection_attempted` (Broker)
- `credential_use_authorized` or `credential_use_denied` (Vault)
- `target_connection_established` (Broker)
- `session_terminated` (Broker)
- `session_termination_failed` (Broker)
These events trace back to the `session_id`, `grant_id`, `user_id`, and `resource_id` without logging any secret material.

## 13. Threat Model

| Threat | Control |
|--------|---------|
| Unauthorized session creation | Sessions can only be created against an ACTIVE JIT grant by the grant owner, verified by Control Plane. |
| Credential Leakage | Broker retrieves credential in-memory, uses it for paramiko/asyncssh auth, and discards it. It is never written to a pipe, log, or user stdout. |
| Token Replay / Session Hijacking | Session tokens are strictly single-use (consumed on connection) and have a short validity window for connection establishment. |
| Generic Proxy Abuse | The SSH server explicitly rejects `tcpip-forward`, `x11-forwarding`, and `agent-forwarding` requests. |
| JIT Bypass | The target OS account has no standing privilege; privilege only exists while the JIT grant is active. |

## 14. Phase Boundaries

- **Phase 10**: Architecture decision, Threat Model, and ADR documentation (This document).
- **Phase 11**: Implement the Worker-hosted SSH broker listener, token validation, basic bridging, and Layer 1 termination.
- **Phase 12**: Implement credential injection using `CredentialUseContext` and full session lifecycle control/recording hooks.

## 15. Deferred Decisions
- Session recording (keystroke logging / video) is deferred to future phases or Phase 12 as it is cosmetic/audit-enhancing, not architectural.

## 16. Verification Plan (Phase 10 Gate 3)
During Phase 11/12 implementation, the following must be verified:
- **Authorization**: Attempt connections with expired tokens, wrong users, and revoked grants. Must strictly DENY.
- **Process Boundary**: Assert via code analysis and tests that the Web API cannot invoke the target connection.
- **Failure Behavior**: Force-crash the broker during an active session and verify JIT revocation engine (Layer 2) still executes.
- **Proxy Restrictions**: Attempt to establish an SSH port forward through the broker. Must be strictly DENIED.

## 17. ACR Required
**NO ACR REQUIRED**. The chosen architecture seamlessly integrates with the frozen Master Plan. It utilizes the mandated 4-plane model, respects the process boundaries, leverages the exact `CredentialUseContext` interface mandated for Vault, and relies on the explicitly defined two-layer termination model.

## 18. Gate 3 Acceptance
This architecture satisfies all frozen security contracts, comprehensively dictates the Broker's implementation parameters for Phases 11/12, and prevents architectural drift.

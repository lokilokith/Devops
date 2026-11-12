# Phase 12 Failure Injection Matrix

| Failure Condition | Expected Backend State | Expected Target State | Expected Audit Event | Safe Retry? | Security Uncertainty? | User-Visible Behavior |
| ----------------- | ---------------------- | --------------------- | -------------------- | ----------- | --------------------- | --------------------- |
| **Vault unavailable** | Session remains PENDING/ACTIVE, connection drops | Privilege remains unchanged (no connection made) | `BROKER_AUTHORIZATION_DENIED` or Error | Yes | No | "Target connection failed" |
| **Credential denied** | Session ACTIVE but connection drops | No connection | `BROKER_AUTHORIZATION_DENIED` | Yes | No | "Authorization denied" |
| **Broker crash** | Session remains ACTIVE in DB, Socket closed | Privilege remains until Expiry Worker cleans it up | None (crash) | Yes | No | Terminal disconnects |
| **Target unavailable** | Session ACTIVE, connection drops | N/A | `BROKER_SESSION_TERMINATED` (Error) | Yes | No | "Target connection failed" |
| **SSH auth failure** | Session ACTIVE, connection drops | N/A | `BROKER_SESSION_TERMINATED` (Error) | Yes | No | "Target authentication failed" |
| **DB failure (Broker)** | Connection drops | N/A | None (DB unavailable) | Yes | No | Connection closed |
| **Network timeout** | Connection drops | Target OS reclaims PTY | `BROKER_SESSION_TERMINATED` | Yes | No | Terminal freezes/closes |
| **Client disconnect** | Session ACTIVE | Target OS reclaims PTY | `BROKER_SESSION_TERMINATED` | Yes | No | Terminal closes |
| **Worker restart** | Session ACTIVE | Orphaned | `jit_reconciliation` | No | Yes (if revocation was running) | Reconnect required |
| **Revoke during session**| Session TERMINATED | JIT privilege removed | `BROKER_SESSION_TERMINATED` | N/A | No | Forcefully disconnected |
| **Duplicate request** | Idempotent | N/A | None / Error | No | No | "Already active/terminated" |
| **Privilege removal fail**| Session TERMINATED / UNCERTAIN | Privilege might remain | `jit_grant_security_uncertainty` | Yes | **Yes** | "Termination failed - Security Uncertainty" |

# Phase 12 Session Invariants

This document strictly defines the required security and lifecycle invariants for privileged access sessions in OpsForge. These must hold true under all concurrent operations, network failures, and race conditions.

### INV-01 — Grant ownership
Every privileged session belongs to exactly one authoritative JIT grant.

### INV-02 — User ownership
The session user must match the authorized grant/access-request user.

### INV-03 — Resource ownership
The session resource must match the resource authorized by the grant.

### INV-04 — Target-account ownership
The session target account must match the active target-account binding authorized by the grant.

### INV-05 — Activation authorization
A session may transition to `ACTIVE` only when the authoritative grant is valid and active.

### INV-06 — No stale authorization
An activation operation must not authorize a session using authorization state that became invalid during the operation. Concurrency mechanisms (such as `with_for_update`) must ensure this.

### INV-07 — Expiry
A session must never remain usable after its authoritative authorization expiry.
`SESSION_USABLE_UNTIL <= AUTHORIZATION_EXPIRY`

### INV-08 — Revocation
Once authorization is revoked, the session cannot regain privileged authorization. Existing active sessions must be forcefully terminated, and new connections using the same authorization must be rejected.

### INV-09 — Isolation
A session token, grant, resource, or target-account binding belonging to one authorization context cannot be used to operate another context.

### INV-10 — Idempotency
Repeated activation, termination, or revocation requests must produce deterministic safe behavior without generating duplicate privileged sessions or dangling connections.

### INV-11 — Auditability
Security-relevant lifecycle transitions must produce authoritative audit evidence without recording secrets (e.g., plaintext credentials or unhashed session tokens).

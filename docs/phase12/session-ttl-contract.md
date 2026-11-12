# Phase 12 Session TTL Contract

This document establishes the hard maximum TTL (Time To Live) contract for privileged JIT sessions.

## 1. Authoritative Timestamps

* **Grant Expiry (`grant.expires_at`)**: The maximum absolute authorization window determined by the policy engine and user request.
* **Session Expiry (`session.expires_at`)**: The explicit termination deadline for an active privileged session.

## 2. Hard Maximum Rule

The fundamental invariants governing TTL are:
1. `session.expires_at <= grant.expires_at`
2. `session.expires_at <= session_start + HARD_MAX_SESSION_TTL`

The `HARD_MAX_SESSION_TTL` is explicitly set to **8 hours**. 

## 3. Calculation & Policy Interaction

When a session is created or a grant is activated, the session's expiry is calculated as:
`min(grant.expires_at, now() + 8_hours)`

If the policy engine restricts the grant to a duration less than 8 hours (e.g., 30 minutes), the session expiry will naturally clamp to the grant's 30-minute expiry.

## 4. Lifecycle Edge Cases

* **Reconnect Behavior**: A client reconnecting to an active session inherits the original `expires_at`. The TTL does NOT reset on reconnect.
* **Client Disconnect**: If a client disconnects, the session remains `ACTIVE` until it is explicitly terminated or reaches its `expires_at` (whichever is earlier).
* **Worker Delay**: If the expiry background worker is delayed, Layer 2 (Target-Side) enforcement might be delayed. However, the worker relies on monotonic database comparisons (`expires_at < now()`) to ensure no missed expirations.
* **Revocation Interaction**: Manual revocation sets the grant to `REVOKED` or `REVOCATION_PENDING`. The broker background task monitors grant status independently of the TTL and will immediately terminate the session regardless of the remaining TTL.

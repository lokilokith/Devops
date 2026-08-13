# Phase 2B.2 — State Management & Domain Lifecycle

## Scope
This phase implemented strict domain-safe state transitions for Vault secrets (rotation lifecycle) and JIT Access sessions, ensuring data consistency, proper idempotency, domain event emission, and robust auditing integration. No actual infrastructure external workers or UI were implemented, focusing purely on solidifying the state-management foundation.

## Implemented Lifecycle Transitions
### Vault State Machine
- **ACTIVE -> ROTATING**: Supported via `begin_rotation()`
- **ROTATING -> ACTIVE**: Supported via `complete_rotation(new_version)`
- **ROTATING -> DESYNCED**: Supported via `fail_rotation()`
- **DESYNCED -> ACTIVE**: Supported via `restore_from_desynced()`
- Invalid transitions (e.g. from DISABLED, or already ROTATING) are deterministic and explicitly rejected.

### JIT State Machine
- **PENDING -> ACTIVE**: Supported natively through grant activation.
- **ACTIVE -> EXPIRED**: Supported and linked dynamically to `JITAccessSession.expire()`.
- **ACTIVE -> REVOKED**: Supported and linked dynamically to `JITAccessSession.revoke()`.
- Invalid transitions are securely rejected.

## Domain Events
Blinker signals were introduced across both modules to enable loosely coupled reaction to domain operations:
- **Vault Lifecycle Events**: `secret_rotation_requested`, `secret_rotation_started`, `secret_rotation_completed`, `secret_rotation_failed`.
- **JIT Events**: `jit_session_created`, `jit_session_expired`, `jit_session_revoked`.

No plaintext credentials or internal secrets leak via event payloads. Events only communicate entity IDs and status context.

## Idempotency Behavior
Idempotent methods have explicit return behaviors rather than failing blindly:
- `JITAccessSession.expire()` & `JITAccessSession.revoke()` return `False` if already expired/revoked, preventing duplicate audit logs and events.
- Domain rules enforce deterministic bounds, avoiding duplicate states in active operations. 

## Audit & Security Verification
- All JIT creation operations proxy Vault permission restrictions and validate ABAC explicitly.
- The `AuditService` logs every sensitive domain action precisely: `SECRET_ROTATION_STARTED`, `SECRET_ROTATION_COMPLETED`, `JIT_SESSION_CREATED`, `JIT_SESSION_REVOKED`, etc. 
- Assertions guarantee no plain text was passed to Audit structures.

## Verification Results

### Focused Test Result
- 7 tests passed (0 failed / 0 errors / 0 warnings).

### Full Regression Result
- 601 passed (6 warnings).
- Baseline was verified without regressions on `phase2-development`.

### Warning Count
- 6 predefined external deprecation/usage warnings (e.g., SQLite in-memory rate limiting and `datetime.utcnow()`). None introduced in this milestone.

### Files Changed
```
app/jit_access/events.py
app/jit_access/models.py
app/jit_access/service.py
app/vault/domain.py
app/vault/events.py
app/vault_lifecycle/service.py
tests/jit_access/test_session_lifecycle.py
tests/vault/test_lifecycle_domain.py
```

### Commit SHA
`db5d0d5`

## Final Verdict
**CERTIFIED**. The Vault Rotation lifecycle and JIT ephemeral access model strictly adhere to Phase 2 requirements, are integrated seamlessly with Audit & Authz services, and pass all idempotency and consistency bounds.

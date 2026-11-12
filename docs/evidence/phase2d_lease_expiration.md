# Phase 2D: Credential Expiration & Lease Concurrency Certification

## Overview
Phase 2D successfully completes the OpsForge Credential Checkout lifecycle by introducing a scheduled background worker that automatically cleans up expired leases (`ExpirationWorker`), while seamlessly handling concurrency with the `RotationWorker`.

## Implemented Features
1. **ExpirationWorker**: An automated system sweep that detects `ACTIVE` leases whose `expires_at` has elapsed, revokes them via `CheckoutService.expire()`, and securely checks them in.
2. **Rotation Deferral**: Modified the `RotationWorker` to proactively exclude `CHECKED_OUT` secrets from rotation eligibility. If a race condition occurs, `RotationWorker` intercepts the conflict and gracefully skips the rotation, recording an `INFO` audit event (`SECRET_ROTATION_DEFERRED`) rather than throwing an exception.
3. **Dedicated CLI Command**: Added `flask checkout process-expirations` to manually trigger the expiration sweep.
4. **Concurrency Hardening**: PostgreSQL `SAVEPOINT`s and atomic `row_version` (CAS) ensure that `RotationWorker`, `ExpirationWorker`, and user-driven check-ins cannot corrupt secret states.

## Testing Matrix Results (654/654 tests passing)

### Component: RotationWorker (Lease Filtering)
- **`test_checked_out_secret_is_excluded_from_eligibility`**: Verified `CHECKED_OUT` secrets are invisible to the policy selector.
- **`test_checked_out_race_produces_deferred_outcome`**: Verified safe `deferred` state when checkouts race against rotation locks.
- **`test_overdue_rotation_becomes_eligible_after_checkin`**: Verified that returning a secret triggers immediate rotation eligibility.

### Component: ExpirationWorker
- **`test_expired_active_lease_is_processed`**: Worker identifies expired leases and invokes check-in logic correctly.
- **`test_non_expired_lease_untouched`**: Active leases are not prematurely expired.
- **`test_terminal_lease_untouched`**: Returned or revoked leases are safely skipped.
- **`test_secret_state_changes_correctly_after_expiration`**: Processed secrets transition back to `ROTATING` status safely.
- **`test_multiple_leases_process_independently`**: Failures in one lease expiration do not prevent subsequent leases from expiring (isolated sub-transactions).

### Component: CLI
- **`test_process_expirations_command_success`**: Manual execution successfully bridges to the `ExpirationWorker`.
- **`test_process_expirations_command_exception_handled_safely`**: Exceptions bubble up as generic CLI failures without exposing underlying data.

## Architectural Notes
- **No Third-Party Queue**: Retained zero-dependency architecture. Expiration operates smoothly through synchronous execution.
- **Audit Compliance**: Rotations interrupted by active checkouts generate non-alarming `SECRET_ROTATION_DEFERRED` logs. `SECRET_ROTATION_FAILED` is reserved strictly for genuine infrastructure or network errors.

## Certification
**Result**: APPROVED. Phase 2D is feature-complete and functionally certified. The Phase 2 PAM lifecycle is structurally complete.

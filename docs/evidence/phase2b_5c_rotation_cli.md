# Phase 2B.5C — Rotation CLI Dispatch Evidence

## Status: CERTIFIED

**Date:** 2026-08-13
**Baseline:** 631 passing tests (Phase 2B.5B certification)
**Final:** 634 passing tests, 0 failures, 0 errors

---

## Objective

Phase 2B.5C provides a MANUAL/EXTERNAL SCHEDULER DISPATCH mechanism. It does NOT implement an internal periodic scheduler (like Celery or APScheduler). The purpose is to provide a thin, secure Flask CLI command (`flask rotate-secrets`) that can be executed by external orchestration tools (cron, Kubernetes CronJob, ECS) to trigger the certified `run_rotation_job` from Phase 2B.5B.

## Architecture & Boundaries

The CLI command is strictly a dependency-wiring and dispatch layer. It respects the boundaries of the certified Phase 2B architecture:

- **No Eligibility Logic**: The CLI does not query or filter `SecretRotationPolicy`. It delegates entirely to `run_rotation_job` which maintains authoritative eligibility checks (`status == ACTIVE` AND `next_rotation_at <= now`).
- **No Concurrency Mechanisms**: The CLI does not implement any distributed locking (e.g., Redis). Overlapping dispatches are safely protected by the Phase 2B.4.1 optimistic locking (CAS via `row_version`), where losing jobs will simply report the policy as "skipped" via a `ConcurrencyError`.
- **KMS Encapsulation**: The CLI correctly utilizes `KMSProviderFactory.resolve_active_provider(session)`. It does not bypass the factory, ensuring that disabled configurations fail closed.
- **Privileged Authorization**: The CLI uses the `_PrivilegedAuthorizationService` (inherited from the worker package) to allow background operations without modifying user RBAC structures.

## CLI Command

```bash
flask rotate-secrets
```

**Outputs:**
The command outputs strictly operational metadata:
```
[2026-08-13T22:30:00+00:00] Starting rotation dispatch...
Rotation job completed.
Attempted:  5
Succeeded:  3
Retryable:  0
Terminal:   1
Skipped:    1
```

## Security Model & Error Handling

- **Credential Hiding**: The CLI never inspects or prints secret bytes, DEKs, or master keys.
- **Exception Sanitization**: If the worker raises an unhandled exception, the CLI catches it, logs it at the `ERROR` level, prints a generic failure message to standard output, and exits with a non-zero code. It specifically avoids dumping traceback contents containing plaintext credentials (verified via a Sentinel test).
- **Idempotency**: Repeated or overlapping calls are completely safe. The first call to successfully CAS update a policy will lock it; subsequent calls during that window will safely `skip` the policy.

## Regression Testing

A focused suite of CLI tests (`tests/cli/test_rotation_commands.py`) verifies the wiring:
1. Verifies exact, single invocation of `run_rotation_job`.
2. Verifies unhandled worker exceptions result in non-zero exit codes without leaking sentinel plaintexts to the CLI output.
3. Verifies no independent DB querying or filtering logic leaks into the CLI layer.

**Results:**
- CLI Tests: 3 passed
- Worker Regression: 17 passed
- Vault Regression: 32 passed
- Full Regression: 634 passed, 0 failures, 0 errors.

KMS regression remains intact (`KMSProviderFactory` logic was untouched).

## Limitations

- The CLI requires the `backend` environment and its dependencies to be fully initialized (i.e. migrations applied). This matches the requirement for any Flask CLI command.
- It does not automatically run on a timer. To achieve continuous rotation, operators must configure an external scheduler (like Kubernetes CronJob) to run `flask rotate-secrets` periodically.

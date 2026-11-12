# Phase 5 Final Certification Report — Automated Rotation Engine

**Phase:** Phase 5 — Automated Rotation Engine  
**Status:** COMPLETE & CERTIFIED  
**Baseline Checkpoint:** `v1.5.0-ssh-rotation` (`fbc510d`)  
**Certification Release:** `v1.6.0-rotation-engine`  
**Date:** 2026-08-31  

---

## 1. Executive Summary

Phase 5 implements the unattended, idempotent, concurrency-safe **Automated Rotation Engine** for OpsForge PAM V1. It turns the certified Phase 4 real SSH rotation mechanism into a robust, scheduled background engine with durable job tracking, worker lease fencing, CAS optimistic locking, bounded exponential backoff retries, explicit crash recovery, and security uncertainty classification.

### Key Architectural Invariants Enforced:
1. **Target-Side Truth Rule:** Database state is never proof that target credential state changed. Real Phase 4 target-side verification (Add → Verify New → Remove Old → Verify Old Rejected → Final Verify New) must succeed before durable database state is committed.
2. **Idempotency & Scheduler Safety:** Database uniqueness constraint `(vault_secret_id, rotation_generation)` guarantees at most one active rotation job per credential generation. Concurrent schedulers race safely without creating duplicate rotations.
3. **Worker Lease Fencing:** Atomic SQL CAS transitions (`QUEUED`/`RETRY_PENDING` $\rightarrow$ `RUNNING`) assign lease ownership and increment `lease_generation`. Stale workers whose leases expire are fenced out and blocked from committing outdated state.
4. **Failure Classification:** Strict classification distinguishes retryable operational failures (e.g. network timeout, transient transport error) with bounded exponential backoff from non-retryable errors (host-key mismatch, invalid configuration) and `SECURITY_UNCERTAINTY` (indeterminate target state, rollback interrupted).
5. **Zero Plaintext Secret Leakage:** Decrypted credentials exist only in memory during the execution step and are immediately released. No private key PEMs, passwords, or secret payloads are ever persisted to jobs, database columns, audit records, or logs.

---

## 2. Architecture & Components

```text
+-----------------------------------------------------------------------------------+
|                            DUE-ROTATION ENGINE / SCHEDULER                        |
|                                                                                   |
|  1. Find active SecretRotationPolicy with next_rotation_at <= now                 |
|  2. Fail-Closed Eligibility: Secret ACTIVE, Resource MANAGED, Binding VALID       |
|  3. Idempotently create RotationJob(vault_secret_id, generation, state=QUEUED)   |
|     (Unique DB constraint prevents concurrent scheduler duplicate jobs)           |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                             ROTATION WORKER PIPELINE                              |
|                                                                                   |
|  1. Atomic Claim (QUEUED/RETRY_PENDING -> RUNNING with worker_id + lease_timeout)  |
|  2. CAS acquire VaultSecret (ACTIVE -> ROTATING, verify version == generation - 1)|
|  3. In-memory decrypt current secret (authorized credential-use pattern)          |
|  4. SSHTargetExecutor.rotate_credential(ExecutionRequest, current_secret)         |
|     - Generate new Ed25519 keypair                                                |
|     - Install new public key to target ~/.ssh/authorized_keys                    |
|     - Independent fresh SSH connection verify new key                             |
|     - Remove old public key from target                                           |
|     - Independent fresh SSH connection verify old key rejected                   |
|     - Final fresh SSH connection verify new key                                   |
|  5. Wipe plaintext references immediately                                         |
|  6. Evaluate result & execute atomic CAS commit:                                  |
|     - SUCCESS: Encrypt new key, Secret ROTATING -> ACTIVE, Job -> SUCCEEDED,      |
|                Policy last_rotated_at = now, next_rotation_at += interval         |
|     - RETRYABLE: Backoff calculation, Job -> RETRY_PENDING, Secret -> ACTIVE,     |
|                  Policy retry_count += 1                                          |
|     - TERMINAL: Job -> FAILED, Secret -> DESYNCED, Policy -> ERROR                |
|     - UNCERTAINTY: Job -> SECURITY_UNCERTAINTY, Secret -> DESYNCED,              |
|                    Policy -> ERROR, P0 audit event (no blind retry)               |
+-----------------------------------------------------------------------------------+
```

---

## 3. Database Schema & Migrations

- **New Model (`app/vault_lifecycle/rotation_job.py`):**
  - Table: `rotation_jobs`
  - Columns: `id`, `vault_secret_id`, `resource_id`, `rotation_generation`, `state`, `attempt_count`, `max_attempts`, `lease_owner`, `lease_expires_at`, `lease_generation`, `started_at`, `completed_at`, `next_retry_at`, `last_error_code`, `last_error_classification`, `correlation_id`, `row_version`, `created_at`, `updated_at`.
  - Unique Constraint: `uq_rotation_jobs_secret_generation` on `(vault_secret_id, rotation_generation)`.
  - Indices on `(state, next_retry_at)` and `(state, lease_expires_at)`.
- **Alembic Migration:**
  - Revision: `e1f2a3b4c5d6` (`migrations/versions/e1f2a3b4c5d6_add_rotation_jobs_table.py`)
  - Down Revision: `7a8b9c0d1e2f`
  - Verified single Alembic head: `['e1f2a3b4c5d6']`.

---

## 4. Test & Verification Evidence

### Test Summary
- **Total Passing Tests:** 851 passing (0 failed, 22 skipped for offline Docker integration target)
- **Code Coverage:** **85.94%** (meets $\ge 85\%$ quality gate)
- **New Unit & Integration Tests:**
  - `tests/vault_lifecycle/test_rotation_job_domain.py`: 9 tests
  - `tests/vault_lifecycle/test_rotation_scheduler.py`: 4 tests
  - `tests/workers/test_rotation_worker_phase5.py`: 11 tests
  - `tests/workers/test_rotation_worker.py`: 19 tests

### Static Analysis & Quality Gates
- **Black:** Clean (0 formatting diffs across `app` and `tests`).
- **isort:** Clean (imports sorted deterministically).
- **Flake8:** Clean (0 lint violations).
- **Ruff:** Clean (0 lint errors).
- **Mypy:** Clean (0 type errors across `app/execution`, `app/vault/ssh_keys.py`, `app/vault_lifecycle`, and `app/workers`).
- **Bandit:** Clean (0 High, 0 Medium issues).
- **pip-audit:** Clean (0 known vulnerabilities found).

---

## 5. Security & Invariant Audit

| Invariant | Implementation Mechanism | Test Verification |
|---|---|---|
| Single Active Job Per Generation | Unique DB constraint on `(vault_secret_id, rotation_generation)` | `test_concurrent_scheduler_race_single_job_created` |
| Worker Lease Fencing | `lease_generation` increment and pre-commit fencing verification | `test_stale_worker_fencing_rejection` |
| Idempotent Claim | SQL CAS update with `row_version` matching | `test_concurrent_worker_race_single_claim` |
| Crash Recovery (Pre-Mutation) | Stale lease detection (`lease_expires_at < now`) and automated reclaim | `test_crash_recovery_before_target_mutation_reclaimed` |
| Security Uncertainty | Explicit `SECURITY_UNCERTAINTY` state for indeterminate target conditions | `test_security_uncertainty_classification` |
| Bounded Exponential Backoff | $2^{\text{attempt}-1} \times 30\text{s}$ calculation, `RETRY_EXHAUSTED` terminal state | `test_retryable_operational_failure_and_backoff`, `test_retry_exhaustion_moves_to_failed` |
| Zero Plaintext Leakage | In-memory key lifecycle, sanitized error codes/messages, zero PEM in DB/audit/logs | `test_zero_plaintext_leakage`, `test_sanitize_error_message_redaction` |
| Bootstrap Credential Lifecycle | Standardized automated rotation through the unified engine | `test_automated_bootstrap_rotation` |

---

## 6. Phase Boundary Verification

Phase 5 adheres strictly to the canonical roadmap:
- **Phase 6 (Target Account Provisioning):** NOT implemented.
- **Phase 7 (JIT Privilege Elevation):** NOT implemented.
- **Phase 8 (JIT Revocation):** NOT implemented.
- **Phase 9 (General Reconciliation):** NOT implemented (only rotation-specific recovery).
- **Phase 10+ (Brokered Sessions, Session Control):** NOT implemented.

---

## 7. Certification Release

- **Certified Commit:** HEAD on `phase5-development`
- **Canonical Tag:** `v1.6.0-rotation-engine`
- **Quality Status:** CERTIFIED

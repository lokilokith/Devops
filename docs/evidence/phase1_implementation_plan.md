# Phase 1 Implementation Plan — Architecture Contract & Execution Plane Foundation

## Target Tag: `v1.2.0-architecture-contract`

### 1. Repository Mapping

| Phase 1 requirement | Existing repository evidence | Required implementation | Files affected | Decision |
|---|---|---|---|---|
| **Execution Plane Contract** | `app/vault/executor.py` had a rotation-only 2-method stub | Create canonical Execution Plane domain model with `ExecutionRequest`, `ExecutionResult`, `ExecutionOperation` (6 operations), `ExecutionStatus`, `FailureClassification`, `VerificationStatus`, and `ExecutionAuthorizationContext` | `app/execution/__init__.py`, `app/execution/domain.py` | Create dedicated `app/execution/` module; extend `app/vault/executor.py` to maintain backwards compatibility |
| **6-Method Executor Abstraction (Gate 1)** | `app/vault/executor.py` had legacy `execute()` | Formalize `TargetExecutor` / `CredentialExecutor` protocol with 6 canonical operations: `validate_target`, `provision_account`, `remove_account`, `rotate_credential`, `apply_jit_grant`, `revoke_jit_grant` + `can_execute` | `app/execution/executor.py`, `app/vault/executor.py` | Define protocol in `app/execution/executor.py`; provide `StubTargetExecutor` and backwards-compatible adapters |
| **Typed Execution Exceptions** | Generic `RuntimeError` was used with string parsing | Define explicit typed exception hierarchy (`TargetAuthenticationError`, `TargetAuthorizationError`, `ExecutionTimeoutError`, `TransportError`, `TargetExecutionError`, `VerificationFailureError`, `SecurityUncertaintyError`, `InvalidExecutionContextError`) with secret sanitization | `app/execution/exceptions.py` | Create `app/execution/exceptions.py` |
| **Execution Authorization Context** | Ad-hoc IDs passed to functions | Enforce typed authorization proof binding (`session_id`, `grant_id`, `user_id`, `resource_id`, `target_account_binding_id`, `credential_id`, `requested_at`, `expires_at`, `permissions`) evaluated on UTC wall-clock time | `app/execution/domain.py` | Embed strict validation inside `ExecutionAuthorizationContext` |
| **Worker / Process Boundary** | Single monolith process in dev, no network hop | Enforce boundary contract: Web/API holds Control + Vault, Worker holds Execution + Session; no plaintext across boundary; no generic `decrypt()` API | `app/execution/domain.py`, `app/vault/credential_use.py` | Define boundary contracts in execution and vault packages |
| **Credential Security Contract (Item 14.1)** | `VaultService.retrieve_secret` existed | Define narrow authorized credential-use operation (`CredentialUseService`) requiring complete authorization binding | `app/vault/credential_use.py` | Add `app/vault/credential_use.py` in Vault Plane |
| **Execution Audit Contract** | `app/audit/service.py` existed | Define execution-plane audit event formatting that strictly excludes credentials, private keys, and plaintext payloads | `app/execution/audit.py` | Create `app/execution/audit.py` integrating with existing `AuditService` |
| **KMS Contract Stub (Gate 1)** | `app/vault/crypto.py` had `KMSProvider` | Establish formal KMS contract stub and verification for Gate 1 | `app/vault/kms_contract.py` | Add `app/vault/kms_contract.py` |

### 2. Implementation Steps

1. Create `app/execution/__init__.py` and `app/execution/domain.py` defining all typed execution models.
2. Create `app/execution/exceptions.py` defining sanitized, typed exception hierarchy.
3. Create `app/execution/executor.py` with 6-method protocol, `StubTargetExecutor`, and updated `ExecutorRegistry`.
4. Update `app/vault/executor.py` and `app/vault/executor_stub.py` to maintain full backwards compatibility for existing rotation tests while adopting the canonical protocol.
5. Create `app/execution/audit.py` for execution event auditing without secret leakage.
6. Create `app/vault/credential_use.py` formalizing Master Plan Item 14.1's bound credential-use contract.
7. Create `app/vault/kms_contract.py` for Gate 1 KMS contract verification.
8. Add comprehensive tests in `tests/execution/`, `tests/vault/test_credential_use.py`, and `tests/vault/test_kms_contract.py`.
9. Run full regression suite (`pytest` with coverage >= 85%), static quality (`black`, `isort`, `flake8`, `ruff`), and security scanners (`bandit`, `pip-audit`).
10. Perform Phase 1 Security Review and produce Phase 1 Acceptance Gate Report.
11. Commit and tag `v1.2.0-architecture-contract`.

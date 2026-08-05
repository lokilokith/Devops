# Phase 1: Credential Vault Foundation
## Testing Strategy

### 1. Overview
This document outlines the testing strategy for the Vault Domain to achieve the required $\ge$90% coverage and ensure zero regressions in the Phase 0 baseline.

### 2. Unit Tests
- **Target Coverage**: $\ge$90%
- **Scope**:
  - `SecretDomainService`: Validating domain invariants, lifecycle state transitions, and business rule enforcement.
  - `SecretFactory`: Ensuring aggregate construction correctly packages metadata and correctly defaults statuses.
  - `EncryptionService`: Validating AES-256-GCM mechanics independently of the external Key Provider by mocking the `MasterKeyProvider` protocol.
- **Tooling**: `pytest`.

### 3. Integration Tests
- **Scope**:
  - Validating the end-to-end integration: `API` &rarr; `Vault Application Service` &rarr; `Repository`.
  - Testing the full `Secret` persistence lifecycle against a test PostgreSQL/SQLite database.
  - Validating the Event Bus correctly publishes `SecretCreated` and `SecretAccessed` events to the Audit Service.
- **Test Scenarios**:
  - Secret retrieval with an `APPROVED` Access Request.
  - Secret retrieval denied due to missing/invalid Access Request (triggers `SecretAccessDenied`).

### 4. Security & Cryptographic Tests
- **Scope**:
  - **Tampering Verification**: Modifying the ciphertext byte array in the test database and verifying that the `EncryptionService` raises a `DecryptionFailedError` instead of returning garbage plaintext.
  - **Substitution Verification**: Modifying the AAD / `encryption_context` in the database and verifying decryption failure.
  - **Memory/Logging Check**: Automated CI checks ensuring `logging.info(payload)` or similar leaks do not exist.
- **Execution**: These tests will run automatically as part of the CI pipeline security stage.

### 5. Performance & Concurrency Tests
- **Scope**:
  - Validating the non-functional requirement target: Cryptographic overhead $<50ms$.
  - Load testing secret retrieval endpoints to ensure the Vault API meets the $<200ms$ target latency under concurrent load.
  - **Concurrent Retrieval**: Ensuring high-volume parallel reads do not introduce race conditions in the Encryption Service.
  - **Concurrent Rotation (Optimistic Locking)**: Forcing parallel rotation attempts on the same secret to validate that the `row_version` optimistic locking mechanism successfully rejects conflicts and prevents data corruption.
- **Tooling**: `locust` or `pytest-benchmark`.

### 6. Regression Strategy
- **Phase 0 Baseline**: The entire 511-test suite from Phase 0 must run seamlessly alongside the new Vault tests.
- **Isolation**: Vault integration tests will use mocked Phase 0 identities or explicit isolated test fixtures to avoid polluting the core security tables.

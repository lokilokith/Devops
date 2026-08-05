# Phase 1: Credential Vault Foundation
## Functional & Non-Functional Requirements

### 1. Functional Requirements

#### FR-01: Secret Lifecycle Management
- **FR-01.1 (Create)** [Priority: MUST]: The system must allow authorized administrators to securely create and store a new credential (secret) within the vault.
- **FR-01.2 (Read)** [Priority: MUST]: The system must allow authorized users to retrieve and decrypt a stored secret.
- **FR-01.3 (Update)** [Priority: MUST]: The system must allow authorized administrators to update/rotate an existing secret, generating a new version of the encrypted payload.
- **FR-01.4 (Delete/Disable)** [Priority: MUST]: The system must allow authorized administrators to logically delete (tombstone) or disable a secret, preventing any further retrieval.

#### FR-02: Resource Association
- **FR-02.1** [Priority: MUST]: Every vault secret SHALL reference exactly one Resource entity from the Phase 0 domain model.
- **FR-02.2** [Priority: MUST]: The system must enforce that a secret cannot exist without a valid linkage to a recognized Resource.

#### FR-03: Encryption & Key Management Placeholder
- **FR-03.1** [Priority: MUST]: The system must encrypt the credential payload before it is written to the persistent storage layer.
- **FR-03.2** [Priority: MUST]: The system must decrypt the payload in memory only at the moment of authorized retrieval.
- **FR-03.3** [Priority: MUST]: The system must support the ability to rotate the Master Encryption Key in the future, maintaining a key identifier or version associated with each encrypted payload.
- **FR-03.4** [Priority: MUST]: Encryption metadata must include `key_version`, `algorithm`, `created_at`, and `encryption_context` (AAD) to facilitate future key rotation and mitigate ciphertext substitution attacks.

#### FR-04: Policy-Driven Retrieval
- **FR-04.1** [Priority: MUST]: Secret retrieval requests shall be evaluated by the Policy Engine.
- **FR-04.2** [Priority: MUST]: Where policy requires approval, an `APPROVED` `AccessRequest` must exist before decryption is permitted.

#### FR-05: Audit & Event Integration
- **FR-05.1** [Priority: MUST]: Every interaction with the vault (creation, decryption, update, deletion) must be published as a domain event.
- **FR-05.2** [Priority: MUST]: The system must emit a `SecretAccessDenied` event when an unauthorized retrieval attempt occurs.
- **FR-05.3** [Priority: MUST]: All vault domain events must be immutably recorded by the `AuditService`.
- **FR-05.4** [Priority: MUST]: Audit logs for secret retrieval must capture the User ID, Resource ID, Access Request ID (if applicable), and timestamp.

### 2. Non-Functional Requirements

#### NFR-01: Security & Cryptography
- **NFR-01.1** [Priority: MUST]: No plaintext secret data shall ever be logged, cached, or written to persistent storage (e.g., databases, swap space).
- **NFR-01.2** [Priority: MUST]: All encryption at rest must use industry-standard algorithms, specifically AES-256 in GCM mode (Authenticated Encryption).
- **NFR-01.3** [Priority: MUST]: The cryptographic implementation must be resistant to timing attacks and tampering.
- **NFR-01.4** [Priority: SHOULD]: Memory containing plaintext secrets must be explicitly cleared as soon as the API response is dispatched (where feasible in Python).

#### NFR-02: Performance & Latency
- **NFR-02.1** [Priority: SHOULD]: Target overhead for cryptographic operations (encryption/decryption) is <50ms per transaction.
- **NFR-02.2** [Priority: SHOULD]: Target response time for Vault API retrieval operations is <200ms under normal load. Performance targets shall be firmly established during performance validation.

#### NFR-03: Compatibility & Stability
- **NFR-03.1** [Priority: MUST]: Phase 1 implementation must not introduce breaking changes to any Phase 0 API schemas or database models.
- **NFR-03.2** [Priority: MUST]: The vault module must maintain independence, ensuring that a failure in the vault subsystem does not crash the identity or routing engines.

#### NFR-04: Testability & Quality
- **NFR-04.1** [Priority: MUST]: The newly implemented Vault Domain must achieve and maintain >=90% code coverage.
- **NFR-04.2** [Priority: MUST]: Security tests must be an automated part of the CI pipeline.
- **NFR-04.3** [Priority: MUST]: Cryptographic boundaries must be fully mockable to support CI/CD pipeline tests without requiring live Master Keys.
- **NFR-04.4** [Priority: MUST]: All 511 tests from the Phase 0 regression suite must continue to pass.

#### NFR-05: Compliance
- **NFR-05.1** [Priority: MUST]: The architecture and data schemas must be designed to align with NIST guidelines for cryptographic standards.
- **NFR-05.2** [Priority: MUST]: The system must enforce strong separation of duties, supporting SOC 2 and ISO 27001 readiness, by ensuring no single administrator can retrieve a secret without explicit access approval (where policy mandates it).

### 3. Traceability Matrix

| Requirement | Architecture / Domain | Target Test Case |
| ----------- | --------------------- | ---------------- |
| **FR-01.1** | Vault Service | `test_create_secret` |
| **FR-01.2** | Vault Service | `test_retrieve_secret` |
| **FR-01.3** | Vault Service | `test_rotate_secret` |
| **FR-01.4** | Vault Service | `test_disable_secret` |
| **FR-02.1** | Vault Domain Model | `test_secret_resource_linkage` |
| **FR-03.1** | Encryption Service | `test_encrypt_secret_payload` |
| **FR-03.2** | Encryption Service | `test_decrypt_secret_payload` |
| **FR-03.4** | Vault Domain Model | `test_secret_metadata_persisted` |
| **FR-04.1** | Policy Engine | `test_secret_retrieval_policy_evaluation` |
| **FR-04.2** | Approval Workflow | `test_secret_retrieval_requires_approved_request` |
| **FR-05.1** | Event Publisher | `test_vault_domain_events_published` |
| **FR-05.2** | Audit Service | `test_secret_access_denied_event` |
| **FR-05.3** | Audit Service | `test_secret_audit_recording` |
| **NFR-01.1**| Security Testing | `test_no_plaintext_in_db` |
| **NFR-01.2**| Encryption Service | `test_aes_gcm_algorithm_used` |
| **NFR-04.2**| CI Pipeline | `ci_security_scan` |

# Phase 1: Credential Vault Foundation
## Threat Model (STRIDE)

### 1. Overview
This threat model evaluates the Vault domain against the STRIDE methodology to ensure the architecture robustly defends against anticipated attacks.

### 2. Trust Boundaries
- **Boundary 1**: External Client &rarr; API Gateway (HTTPS TLS 1.3)
- **Boundary 2**: API Gateway &rarr; Vault Application Service (Internal Network / App context)
- **Boundary 3**: Vault Application Service &rarr; Master Key Provider
- **Boundary 4**: Vault Application Service &rarr; Database Repository

### 3. STRIDE Analysis

#### 3.1 Spoofing
- **Threat**: An attacker impersonates a legitimate administrator to retrieve a secret.
- **Mitigation**: Strict enforcement of Phase 0 Identity (JWT verification) and Policy Engine checks. All requests require valid cryptographic signatures on the token.

#### 3.2 Tampering
- **Threat**: An attacker with database access alters the encrypted credential.
- **Mitigation**: Envelope encryption utilizes `AES-256-GCM` (Authenticated Encryption). Any tampering will cause tag verification to fail during decryption, resulting in a `DecryptionFailedError` and denied access.

#### 3.3 Repudiation
- **Threat**: An administrator retrieves a secret and later denies doing so.
- **Mitigation**: The Vault Service emits domain events (`SecretAccessed`, `SecretAccessDenied`) that the immutable Audit Service independently records.

#### 3.4 Information Disclosure
- **Threat**: Plaintext secrets are exposed via database dumps, memory scraping, or application logging.
- **Mitigation**:
  - Zero plaintext persistence (Database stores only Ciphertext & Encrypted DEK).
  - Explicit memory wiping hints for plaintext variables in the Application Service.
  - Strict code-review gates preventing logging of DTO payloads.

#### 3.5 Denial of Service
- **Threat**: Repeated brute-force retrieval requests exhaust cryptographic resources.
- **Mitigation**: API rate limiting (inherited from Phase 0) and the fast failure of Policy checks before expensive cryptographic decryption occurs.

#### 3.6 Elevation of Privilege
- **Threat**: A low-privileged user attempts to rotate a master key or bypass the approval workflow.
- **Mitigation**: Multi-stage RBAC enforcement (`@requires_permission`) plus secondary Access Request approval verification via the Policy Engine.

### 4. Ciphertext Substitution (Specific Attack)
- **Threat**: A malicious DB admin swaps the ciphertext of an authorized secret with one they don't have access to, attempting to read a different payload under their allowed resource.
- **Mitigation**: The `encryption_context` (containing `secret_id` and `resource_id`) is bound as Additional Authenticated Data (AAD). A swapped ciphertext will fail decryption AAD validation.

### 5. Residual Risks
- **Master Key Provider Compromise**: A breach of the external Key Provider (e.g., leaked AWS KMS credentials) could lead to offline decryption if the database is simultaneously compromised.
- **Insider Misuse**: Authorized administrators with legitimate approval could misuse retrieved credentials. This risk is mitigated post-retrieval by Phase 0 Audit logging, but not prevented technically by the Vault.
- **Operational Failures**: Accidental deletion of the Master Key or irreversible loss of database backups resulting in permanent cryptographic data loss (crypto-shredding).

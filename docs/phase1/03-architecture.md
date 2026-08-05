# Phase 1: High-Level Architecture
## Credential Vault Foundation

### 1. Architectural Overview
The Phase 1 architecture integrates a highly secure Credential Vault within the certified Phase 0 boundaries of the OpsForge Platform. Adhering to Domain-Driven Design (DDD), the Vault is introduced as an independent bounded context (`app/vault`) responsible for the cryptographic lifecycle of secrets.

The architecture strictly adheres to event-driven paradigms and policy-driven authorization, ensuring that the Vault does not bypass or subvert Phase 0 RBAC and audit controls.

### 2. System Context
- **OpsForge API Gateway**: Routes incoming secret lifecycle operations to the Vault module.
- **Phase 0 Policy Engine**: Intercepts read/write requests to validate authorization contexts, including checking for an `APPROVED` `AccessRequest` if policy mandates.
- **Vault Domain**: The new boundary containing APIs, Services, and Data layers specifically for secrets.
- **Phase 0 Resources Domain**: Secrets are explicitly linked to the preexisting Resource entities, keeping resource management decoupled from secret storage.
- **Event Bus**: Asynchronous message bus used for publishing domain events to downstream consumers (Audit, Notifications).

### 3. Component Architecture
The Vault architecture is logically decoupled into the following layers:

#### 3.1 Vault API (Presentation Layer)
- Handles HTTP request validation.
- Maps JSON DTOs to Domain objects.
- Does not contain any business or cryptographic logic.

#### 3.2 Vault Application Service (Application Layer)
- Orchestrates the use cases (Create, Read, Rotate, Delete).
- Manages transactions and repository interactions.
- Publishes Domain Events to the Event Bus.

#### 3.3 Secret Domain Service (Domain Layer)
- Encapsulates pure business rules for secrets.
- Verifies domain invariants and associations with the `Resource` domain.
- Generates Domain Events (e.g., `SecretCreated`, `SecretAccessed`, `SecretAccessDenied`).

#### 3.4 Encryption Service (Domain Cryptography)
- Dedicated, stateless service responsible purely for encrypting and decrypting payloads.
- Integrates with the Master Key provider.
- Enforces AES-256-GCM envelope encryption.

#### 3.5 Vault Repository (Infrastructure Layer)
- Manages the persistence of encrypted ciphertexts and cryptographic metadata.
- Prevents database-level leakage of plaintext.
- Interfaces with SQLAlchemy to persist the `Secret` domain model.

### 4. Domain Model (High-Level)
The Vault introduces the `Secret` aggregate root, which is strictly associated with the Phase 0 `Resource`.

**Entity: Secret**
- `id`: UUID (Primary Key)
- `resource_id`: UUID (Foreign Key to `Resource`)
- `encrypted_dek`: Bytes (Data Encryption Key encrypted by Master Key)
- `ciphertext`: Bytes (The credential payload encrypted by DEK)
- `key_version`: String (Reference to the Master Key version used)
- `algorithm`: String (e.g., `AES-256-GCM`)
- `status`: Enum (e.g., `ACTIVE`, `ROTATED`, `DISABLED`)
- `created_at`: Timestamp
- `updated_at`: Timestamp

### 5. Trust Boundaries

```text
Boundary 1: External Client &rarr; HTTPS &rarr; API Gateway
Boundary 2: API Gateway &rarr; Authentication (JWT Validation)
Boundary 3: Policy Engine (Authorization) &rarr; Vault API
Boundary 4: Vault Application Service &rarr; Encryption Boundary &rarr; Database
Boundary 5: Vault Domain &rarr; Event Bus &rarr; Audit/Notifications
```

### 6. Interaction Flows

#### 6.1 Secret Creation (Write Flow)
1. API receives plaintext secret and target `resource_id`.
2. Policy Engine validates caller's authorization.
3. Vault Application Service invokes Secret Domain Service to validate `resource_id` existence and domain rules.
4. Vault Application Service delegates payload to Encryption Service.
5. Encryption Service generates DEK, encrypts payload, encrypts DEK using Master Key, and returns ciphertext + metadata.
6. Vault Repository persists the encrypted entity.
7. Vault Application Service publishes `SecretCreated` to the Event Bus.
8. Event Bus routes event to Audit/Notifications.

#### 6.2 Secret Retrieval (Read Flow)
1. API receives request for secret by `resource_id`.
2. Policy Engine intercepts request, querying approval requirements.
3. If approval is required, Policy Engine validates an `APPROVED` `AccessRequest` exists for the caller and resource.
4. If denied, Policy Engine emits `SecretAccessDenied` to the Event Bus.
5. If approved, Vault Application Service retrieves ciphertext from Vault Repository.
6. Encryption Service decrypts the DEK using Master Key, then decrypts ciphertext using DEK.
7. Plaintext returned to API layer.
8. Vault Application Service publishes `SecretAccessed` to the Event Bus.
9. Plaintext lifetime shall be minimized, and secret material shall not be retained beyond the duration required for request processing.

### 7. Cryptographic Architecture
The system strictly employs an **Envelope Encryption** architecture.
- **Data Encryption Key (DEK)**: A unique cryptographic key generated for each secret. The DEK directly encrypts the plaintext payload using `AES-256-GCM`.
- **Master Encryption Key (MEK)**: Managed externally. The MEK encrypts the DEK. The encrypted DEK is stored alongside the ciphertext payload.
- **Storage**: The database stores only the `ciphertext` and `encrypted_dek`, never the plaintext payload or plaintext DEK.

### 8. Security & Compliance Enforcement
- **Zero Plaintext Persistence**: Enforced by the absolute separation of the Encryption Service from the Repository layer. The Repository only ever receives the resulting ciphertext and encrypted DEK.
- **Traceability**: Realized by Event-Driven Architecture. The Vault Service does not write to the Audit table directly; it publishes events to the Event Bus, guaranteeing consistent compliance logging.

### 9. Future Extension Points
The architecture is designed to support the following Phase 2/3 capabilities:
- **KMS Provider**: Integration with AWS KMS / Azure Key Vault / HashiCorp Vault for Master Key management.
- **HSM Provider**: Integration with Hardware Security Modules.
- **Password Rotation**: Automated rotation of endpoint credentials.
- **Just-In-Time (JIT)**: Dynamic credential generation.
- **Session Recording**: SSH/RDP brokering and recording.
- **SIEM Integration**: Exporting Audit events to external Security Information and Event Management systems.

# Phase 1: Credential Vault Foundation
## Domain Model

### 1. Overview
The Vault Domain Model encapsulates the core business rules, entities, and events related to secret management. It sits at the core of the Vault Application Service and strictly adheres to Domain-Driven Design (DDD) principles.

### 2. Aggregates and Entities

#### Aggregate Root: `Secret`
The primary aggregate root representing a privileged credential associated with a resource. It explicitly owns its metadata and version history.

**Attributes:**
- `id`: UUID (Identifier)
- `resource_id`: UUID (Reference to Phase 0 Resource)
- `status`: `SecretStatus` (Enum)
- `active_version`: `SecretVersion` (Entity)
- `metadata`: `SecretMetadata` (Value Object)
- `created_at`: Datetime
- `updated_at`: Datetime

#### Entity: `SecretVersion`
Represents a specific cryptographic generation of the secret payload. While Phase 1 primarily focuses on the active version, this entity ensures the model is prepared for full rotation history.
- `id`: UUID
- `encrypted_dek`: Bytes (Data Encryption Key encrypted by MEK)
- `ciphertext`: Bytes (Payload encrypted by DEK)
- `version_number`: Integer
- `created_at`: Datetime

### 3. Value Objects

#### `SecretMetadata`
Encapsulates all necessary cryptographic metadata required for decryption and rotation.
- `key_version`: String (Identifier for the active MEK)
- `algorithm`: String (e.g., `AES-256-GCM`)
- `nonce`: Bytes (Cryptographic nonce used for payload encryption)
- `encryption_context`: Dict (Optional metadata for Additional Authenticated Data (AAD) with AES-GCM)

#### `SecretStatus`
- `ACTIVE`: The secret is valid and retrievable by authorized users.
- `ROTATING`: The secret is in a transitional state during password rotation (Phase 2).
- `DISABLED`: The secret is administratively disabled and cannot be retrieved.
- `TOMBSTONED`: Logically deleted.

### 4. Domain Invariants and Rules
- **Rule 1**: A `Secret` MUST have a valid, non-null `resource_id`.
- **Rule 2**: A `Secret` in `DISABLED` or `TOMBSTONED` status CANNOT be retrieved or decrypted under any circumstances.
- **Rule 3**: `encrypted_dek` and `ciphertext` MUST NOT be empty or null for any active `SecretVersion`.
- **Rule 4**: A specific `Resource` can have only ONE `ACTIVE` secret at a time (1:1 mapping for Phase 1).
- **Rule 5**: A `Secret` CANNOT change its `resource_id` after creation. Resource association is immutable.
- **Rule 6**: Every `Secret` MUST reference exactly one active `key_version`.

### 5. Domain Services & Factories

#### `SecretFactory`
Responsible for the consistent creation of the `Secret` aggregate to keep creation logic out of controllers and repositories.
- `create_secret(resource_id, payload) -> Secret`: Generates ID, Metadata, encrypts payload, creates Aggregate, and returns Secret.

#### `SecretDomainService`
Encapsulates pure business rules for secrets that span multiple entities.
- **Responsibilities**: Validate invariants, validate lifecycle transitions, validate rotations, raise domain events.

### 6. Repository Contracts

#### `SecretRepository` (Interface)
Defines the persistence contract expected by the Domain, without leaking SQLAlchemy details.
- `save(secret: Secret) -> None`
- `find_by_id(id: UUID) -> Secret | None`
- `find_by_resource(resource_id: UUID) -> Secret | None`
- `disable(id: UUID) -> None`
- `exists(resource_id: UUID) -> bool`

### 7. Domain Events
Domain events are published to the Event Bus to decouple side effects (like Auditing and Notifications) from the core domain logic.

**Common Payload Field**: `correlation_id` (Used for audit correlation, distributed tracing, debugging, and SIEM).

#### `SecretCreated`
- **Payload**: `correlation_id`, `secret_id`, `resource_id`, `timestamp`, `actor_id`
- **Trigger**: Upon successful creation of a new secret.

#### `SecretAccessed`
- **Payload**: `correlation_id`, `secret_id`, `resource_id`, `timestamp`, `actor_id`, `access_request_id` (optional)
- **Trigger**: Upon successful authorized retrieval and decryption.

#### `SecretAccessDenied`
- **Payload**: `correlation_id`, `secret_id` (or `resource_id`), `timestamp`, `actor_id`, `reason`
- **Trigger**: When the Policy Engine or Domain Service rejects a retrieval attempt.

#### `SecretRotated`
- **Payload**: `correlation_id`, `secret_id`, `resource_id`, `timestamp`, `actor_id`, `new_key_version`
- **Trigger**: When an existing secret payload is updated.

#### `SecretDisabled`
- **Payload**: `correlation_id`, `secret_id`, `resource_id`, `timestamp`, `actor_id`
- **Trigger**: Upon administrative disabling of a secret.

#### `SecretDeleted`
- **Payload**: `correlation_id`, `secret_id`, `resource_id`, `timestamp`, `actor_id`
- **Trigger**: Upon transitioning to the TOMBSTONED state.

### 8. Phase 0 Integrations
The Vault Domain maintains a loose coupling with Phase 0 domains via IDs, avoiding direct object references across bounded contexts.
- **Resource Linkage**: Relies strictly on `resource_id`. A `Secret` holds only `resource_id`—no direct ORM object references exist across bounded contexts.
- **Identity Linkage**: Relies strictly on `actor_id`.

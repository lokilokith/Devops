# Phase 1: Credential Vault Foundation
## Database Design

### 1. Overview
This document defines the relational database schema for the Vault Domain. The design is strictly derived from the approved `docs/phase1/04-domain-model.md` and fulfills the requirements set in `docs/phase1/02-requirements.md`. 

The schema acts as the persistence implementation of the `Secret` aggregate and its entities, without modifying the underlying business rules.

### 2. Schema Design

#### Table: `vault_secrets`
Persists the `Secret` aggregate root and its non-versioned metadata.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Unique identifier for the secret. |
| `resource_id` | `UUID` | `UNIQUE, NOT NULL, FOREIGN KEY(resources.id)` | Logical reference to the Phase 0 Resource. A strict database foreign key is used to guarantee referential integrity since both tables exist within the identical PostgreSQL database instance. |
| `current_version_id` | `UUID` | `FOREIGN KEY(vault_secret_versions.id)` | Direct pointer to the active `SecretVersion`, enabling constant-time retrieval of the active payload. Nullable only during aggregate creation initialization. |
| `status` | `VARCHAR(32)` | `NOT NULL` | Enum: `ACTIVE`, `ROTATING`, `DISABLED`, `TOMBSTONED`. |
| `row_version` | `INTEGER` | `NOT NULL, DEFAULT 1` | Optimistic concurrency control lock. Prevents race conditions during concurrent secret rotations or updates. |
| `created_at` | `TIMESTAMP` | `NOT NULL` | Creation time (UTC). |
| `updated_at` | `TIMESTAMP` | `NOT NULL` | Last update time (UTC). |

#### Table: `vault_secret_versions`
Persists the `SecretVersion` entity, representing the cryptographic generations of a secret payload.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Unique identifier for the version. |
| `secret_id` | `UUID` | `FOREIGN KEY(vault_secrets.id), NOT NULL` | Reference to the parent aggregate. |
| `version_number` | `INTEGER` | `NOT NULL` | Sequential version number (1, 2, 3...). |
| `encrypted_dek` | `BYTEA` | `NOT NULL` | The DEK encrypted by the MEK. |
| `ciphertext` | `BYTEA` | `NOT NULL` | The credential payload encrypted by the DEK. |
| `key_version` | `VARCHAR(64)` | `NOT NULL` | Identifier for the MEK used to encrypt the DEK. |
| `algorithm` | `VARCHAR(32)` | `NOT NULL` | Cryptographic algorithm identifier (e.g., `AES-256-GCM`). |
| `nonce` | `BYTEA` | `NOT NULL` | Cryptographic nonce for AES-GCM. |
| `encryption_context` | `JSONB` | `NULLABLE` | Metadata for Additional Authenticated Data (AAD) protection against ciphertext swapping. |
| `created_at` | `TIMESTAMP` | `NOT NULL` | Creation time (UTC). |

*Indexes:*
- `UNIQUE INDEX idx_secret_version (secret_id, version_number)` to enforce strict version sequencing and prevent rotation collisions.

*Migration Strategy Note (Circular Dependency):*
Because `vault_secrets.current_version_id` points to `vault_secret_versions.id` and `vault_secret_versions.secret_id` points to `vault_secrets.id`, Alembic migrations must be carefully ordered:
1. Create `vault_secrets` without the `current_version_id` foreign key constraint.
2. Create `vault_secret_versions`.
3. Alter `vault_secrets` to add the `current_version_id` foreign key constraint.

### 3. Traceability & Consistency Check
This schema maps directly to the Domain Model constraints without reshaping the business model:
- **FR-01 / Domain Rule 3**: `encrypted_dek` and `ciphertext` are explicitly enforced as `NOT NULL` in the versions table.
- **FR-02 / Domain Rule 4 & 5**: `resource_id` has a `UNIQUE` constraint in `vault_secrets`, ensuring a strict 1:1 active mapping and immutability via application rules.
- **FR-03 / Domain Rule 6**: `key_version` and `algorithm` are captured alongside every `encrypted_dek`.
- **Aggregate Boundary Support**: By separating `vault_secrets` and `vault_secret_versions` and providing a `current_version_id` pointer, the persistence layer optimally supports the `SecretVersion` entity ownership hierarchy.

### 4. Zero Plaintext Guarantee
As stipulated by the NFRs, there are absolutely no database columns for plaintext passwords, keys, or sensitive metadata. The database remains completely blind to the contents of the `ciphertext` and `encrypted_dek`.

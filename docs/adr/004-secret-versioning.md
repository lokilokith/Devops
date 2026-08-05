# ADR 004: Explicit Secret Versioning
**Status:** Accepted
**Date:** 2026-08-04

## Context
When a secret is rotated (Phase 2), the old password must be replaced. Overwriting the original payload destroys cryptographic history, breaks active dependent sessions, and hampers potential rollback features.

## Decision
We will introduce a `SecretVersion` entity owned by the `Secret` aggregate. The database will separate `vault_secrets` from `vault_secret_versions`, storing the cryptographic payload exclusively in the version table. A `current_version_id` pointer will track the active version.

## Consequences
- **Positive:** Safe password rotation, explicit tracking of cryptographic generations, and O(1) active payload retrieval.
- **Negative:** Requires a more complex database schema and a precise Alembic migration strategy due to circular foreign key constraints.

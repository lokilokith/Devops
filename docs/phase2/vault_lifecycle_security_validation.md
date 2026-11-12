# Phase 2B.4 Vault Lifecycle - Security Validation

## Security Objectives
The Vault Lifecycle implementation adds deterministic, rules-based logic to manage the lifecycle of a vault secret.

## Validations Performed

1. **IDOR Prevention**
   - The `/vault-lifecycle/policies/<id>` endpoints are guarded by `AuthorizationService`.
   - Access to a lifecycle policy requires explicit permissions on the `vault_lifecycle` namespace via RBAC.
   - Tested in `test_idor_get_policy` (passing).

2. **Privilege Escalation**
   - Endpoints do not allow modifying `vault_secret_id` for existing policies to point to another secret they don't own.
   - Policies can only be created by users with appropriate `vault_lifecycle` create permissions.

3. **Malformed Inputs & Bounds**
   - `rotation_interval_seconds` is validated via Marshmallow schema `validate=validate.Range(min=60)`.
   - Ensures negative intervals or short intervals (e.g. `< 1 minute`) cannot be applied. Tested via `test_malformed_interval_negative` (passing).
   - UUID inputs are safely routed and return 404/400 gracefully on malformation.

4. **Plaintext / Ciphertext Leakage**
   - Lifecycle API endpoints operate strictly on policy metadata (`SecretRotationPolicyResponseSchema`).
   - The underlying Vault API continues to handle encryption and retrieval.
   - Tests assert that `payload` or `plaintext` are not leaked in any lifecycle response (passing).

5. **Rotation Atomicity**
   - `VaultApplicationService.rotate_secret` integrates `VaultLifecycleService.record_rotation`.
   - The timestamps for the lifecycle policy are updated within the exact same `self._session.commit()` as the Vault Secret rotation, ensuring atomicity.

6. **Version Integrity**
   - Rotating a secret appends a new `VaultSecretVersion` and bumps the `current_version_id`.
   - The original ciphertext is preserved.
   - Confirmed via `test_vault_rotation_updates_lifecycle_policy`.

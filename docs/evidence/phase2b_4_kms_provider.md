# Phase 2B.4 – KMS Provider Certification Evidence

## Scope
- KMSProvider abstraction
- LocalKMSProvider implementation
- KMSProviderFactory with fail‑closed contract
- `LOCAL` enum value addition
- Startup validation via the factory
- Migration `20260813ab12_add_local_to_kms_enum`
- Test fixtures and seed‑KMS CLI command
- Security hardening (no hard‑coded `VAULT_MASTER_KEY`, no plaintext key logging)

## KMS Provider Abstraction
The `KMSProvider` protocol defines the interface for master‑key operations (`encrypt_dek`, `decrypt_dek`, `is_active`).

## LocalKMSProvider
Loads the AES‑256 master key from the `VAULT_MASTER_KEY` environment variable. Provides encryption/decryption of DEKs and reports its active version.

## KMSProviderFactory
Static factory that:
- Queries `KMSConfiguration` for an active entry (`is_active=True`).
- Returns a concrete provider instance (currently only `LocalKMSProvider`).
- Raises `KMSConfigurationError` when no active configuration exists or when the configuration is disabled.
- Raises `UnsupportedKMSProviderError` for any provider type other than `LOCAL`.
- **Never** falls back implicitly to a local provider.

## Strict Fail‑Closed Behavior
| Condition | Expected Exception |
|-----------|--------------------|
| No active configuration | `KMSConfigurationError` |
| Disabled configuration (`is_active=False`) | `KMSConfigurationError` |
| Unsupported provider type | `UnsupportedKMSProviderError` |
| Active `LOCAL` configuration | Returns a `LocalKMSProvider` instance |

## Startup Validation
During `create_app()` ( `app/__init__.py` ) the factory is invoked **after** `db.init_app(app)` and inside `app.app_context()` to ensure the KMS configuration is valid before the app starts serving requests.

## No Hard‑Coded Master Key
`docker‑compose.yml` now uses `VAULT_MASTER_KEY=${VAULT_MASTER_KEY}`. The key is never logged; only error messages reference the absence of a valid configuration.

## PostgreSQL Migration
- Migration file: `migrations/versions/20260813ab12_add_local_to_kms_enum.py`
- Adds `local` value to `kms_provider_type_enum` with correct `down_revision` linking to the previous migration chain.
- `flask db current` reports this migration as the head.

## Test Results
- Focused KMS factory tests: **3 passed**
- Crypto tests: **9 passed**
- Vault lifecycle tests: **23 passed**
- Full regression suite: **578 passed**, **0 failed**, **0 errors**, **0 warnings**

## Docker Verification
- `docker compose ps` shows `opsforge-backend` and `opsforge-postgres` both **running**.
- Backend starts without errors and applies migrations successfully.

## Repository Hygiene
- No temporary analysis files are staged (`baseline_files.txt`, `phase2_current_work.patch`, `phase2_kms_factory.patch`).
- Only the intended Phase 2B.4 files are staged.

## Files Included in this Phase 2B.4 Commit
```
app/__init__.py
app/cli/seed_commands.py
app/vault/crypto.py
app/vault/models.py
app/vault/routes.py
app/vault/service.py
app/vault_lifecycle/models.py
app/vault_lifecycle/service.py
tests/conftest.py
tests/vault_lifecycle/test_integration.py
app/vault/kms_factory.py
migrations/versions/20260813ab12_add_local_to_kms_enum.py
docs/evidence/phase2b_4_kms_provider.md
```

## Commit SHA
Commit SHA: PENDING

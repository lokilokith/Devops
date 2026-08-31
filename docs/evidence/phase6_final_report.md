# OpsForge PAM V1 — Phase 6 Target Account Provisioning Final Report & Certification

## 1. Executive Summary

Phase 6 (**Target Account Provisioning**) implements real per-human, per-target OS identity provisioning for OpsForge PAM V1, building upon the certified Phase 5 baseline (`v1.6.0-rotation-engine`).

Target account provisioning establishes individual target-side OS identities linked to Control Plane users, eliminating shared administrative accounts while enforcing least privilege and forensic traceability. Target account creation is performed lazily upon the first approved access request on a resource, managed via a dedicated target-side helper boundary, independently verified over SSH, and maintained through an explicit lifecycle.

**Canonical Tag**: `v1.7.0-account-provisioning`  
**Base Milestone**: `v1.6.0-rotation-engine` (`1ff3d7e8041aa593e0330252a00ac8ea2aaeddd3`)  
**Development Branch**: `phase6-development`

---

## 2. Architecture & Data Model

### 2.1 Permanent Target Abstraction: `Resource`
In accordance with the frozen architecture invariants, `Resource` remains the permanent target abstraction representing machines/endpoints. No extraneous target entities were introduced.

### 2.2 `TargetAccountBinding` Data Model
Located in `app/target_accounts/models.py`, `TargetAccountBinding` stores the association between a Control Plane user and a dedicated OS account on a target resource.

* **Schema Invariants & Constraints**:
  - `unique(control_plane_user_id, resource_id)`: A control plane user has at most one target OS account per resource.
  - `unique(resource_id, target_os_username)`: Two control plane users NEVER share a target OS username on the same resource.
  - `control_plane_user_id` $\to$ `users.id` (FK ON DELETE RESTRICT)
  - `resource_id` $\to$ `resources.id` (FK ON DELETE RESTRICT)
  - `ssh_credential_id` $\to$ `vault_secrets.id` (FK ON DELETE SET NULL)
  - `status`: Enum (`PENDING`, `ACTIVE`, `SUSPENDED`, `REMOVED`)
  - `last_verified_at`: Timestamp of most recent independent verification
  - `failure_reason`: Diagnostic message if provisioning or verification failed

### 2.3 Alembic Database Migration
* Migration Script: `migrations/versions/f2a3b4c5d6e7_add_target_account_bindings.py`
* Down Revision: `e1f2a3b4c5d6` (Phase 5 rotation job state table)
* Single Migration Head Confirmed: `['f2a3b4c5d6e7']`

---

## 3. Deterministic Username Derivation

Located in `app/target_accounts/username.py`:
* Normalizes the control plane username to POSIX-compliant characters `[a-z0-9_-]`.
* Length bounded to $\le 32$ characters.
* Prepends safe prefix `u_` if the normalized name starts with a digit, symbol, or matches protected system accounts (`root`, `opsforge-svc`, `bin`, `daemon`, `nobody`, `sshd`, etc.).
* Resolves collisions deterministically on the resource by appending sequential numeric suffixes (`_1`, `_2`, ...), preserving character limits.
* Rejects path traversal attempts (`..`, `/`) and null bytes (`\x00`).

---

## 4. Helper Boundary & Execution Plane

### 4.1 Target Helper Invocation Boundary
* Provisioning operates through the pre-installed root-owned helper executable `/usr/local/sbin/opsforge-helper`.
* The control plane connects as bootstrap service user `opsforge-svc` (presenting the rotated bootstrap private key) and runs:
  ```bash
  sudo -n /usr/local/sbin/opsforge-helper provision_account <target_os_username> '<public_key>'
  ```
* `opsforge-svc` possesses strict, bounded `sudoers` rights permitting only `/usr/local/sbin/opsforge-helper` without passwords. `opsforge-svc` cannot edit arbitrary files or grant standing sudo.

### 4.2 Helper Security Actions
The helper:
1. Validates username against POSIX safety rules and system blacklist.
2. Creates the target OS user: `useradd -m -s /bin/bash <target_os_username>`.
3. Immediately locks the account password: `usermod -L <target_os_username>`.
4. Creates `~/.ssh/authorized_keys` with strict permissions (`0700` directory, `0600` file, owned by the new user).
5. Appends the entry to `/var/lib/opsforge/ownership_manifest.json`.
6. Self-verifies user creation locally.

### 4.3 Target Removal Boundary
Removal is executed via:
```bash
sudo -n /usr/local/sbin/opsforge-helper remove_account <target_os_username>
```
The helper terminates active processes (`pkill -u`), removes the account and home directory (`userdel -r`), and cleans manifest tracking. The execution plane verifies removal by testing `id <target_os_username>` (must return exit code $\ne 0$).

---

## 5. Independent Target Verification

Before marking any binding `ACTIVE`, the Control Plane performs mandatory independent target-side verification:
1. Opens a **fresh SSH connection** presenting **ONLY** the newly generated human private key (without using bootstrap credentials).
2. Executes and verifies target invariants:
   - `whoami`: Verified to match `target_os_username`.
   - `echo $SHELL`: Verified to match `/bin/bash`.
   - `sudo -n true`: Verified to **FAIL** (must return non-zero exit code, confirming zero standing sudo).
3. If any verification check fails, the binding is transitioned to `PENDING` with failure classification `UNCERTAIN_STATE` and logged as a `CRITICAL` audit event.

---

## 6. Zero Plaintext Secrecy & Security Controls

* **Private Key Material**: Generated ephemerally in memory using `cryptography.hazmat.primitives.asymmetric.ed25519`. Private keys are immediately wrapped via Vault KMS envelope encryption (`AES-256-GCM` with AAD) and persisted only in `vault_secrets`/`vault_secret_versions`. In-memory string variables are deleted/zeroized immediately after use.
* **Audit Logging**: All lifecycle events (`target_account.provisioned`, `target_account.provision_failed`, `target_account.suspended`, `target_account.removed`) log structured metadata (user ID, resource ID, target username, credential ID, correlation ID) and strictly omit private keys or secret material.
* **IDOR Protection & Authorization**: API endpoints (`/target-accounts`) verify user ownership and require explicit RBAC permissions (`PERM_TARGET_ACCOUNTS_READ`, `PERM_TARGET_ACCOUNTS_DELETE`) for cross-user administration.

---

## 7. Phase Boundary Verification

Phase 6 maintains strict architectural boundaries:
* **Phase 7 (JIT Privilege Elevation)**: `SSHTargetExecutor.apply_jit_grant` raises `NotImplementedError`.
* **Phase 8 (JIT Revocation)**: `SSHTargetExecutor.revoke_jit_grant` raises `NotImplementedError`.
* **Phase 9 (Reconciliation)** & **Phase 10+ (Session Brokering)**: Not present or exposed.
* Verified via `tests/test_phase6_boundaries.py` and `tests/execution/test_ssh_executor.py`.

---

## 8. Quality, Static Analysis, and Security Gates

| Gate | Tool | Status | Details |
|---|---|---|---|
| Import Sorting | `isort` | PASSED | 0 formatting issues across `app/` and `tests/` |
| Code Formatting | `black` | PASSED | 100% compliant across codebase |
| Linting | `flake8` | PASSED | 0 lint or PEP8 violations |
| Linting & Checking | `ruff` | PASSED | All checks passed |
| Static Type Checking | `mypy` | PASSED | Success: 0 issues in `app/target_accounts` |
| Security AST Scan | `bandit` | PASSED | 0 Medium/High security vulnerabilities |
| Dependency Audit | `pip-audit` | PASSED | 0 known CVEs across all dependencies |
| Database Migrations | `alembic` | PASSED | Single migration head `['f2a3b4c5d6e7']` |

---

## 9. Comprehensive Test Suite & Coverage

* **Total Test Count**: **879 passed**, 0 failed, 23 skipped
* **Total Line Coverage**: **85.09%** (exceeds mandatory $\ge 85.0\%$ gate)
* **Phase 6 Test Suites**:
  - `tests/target_accounts/test_binding_model.py`: 4 passed
  - `tests/target_accounts/test_username_derivation.py`: 6 passed
  - `tests/target_accounts/test_target_account_service.py`: 6 passed
  - `tests/target_accounts/test_target_account_routes.py`: 6 passed
  - `tests/ownership/test_target_account_ownership.py`: 1 passed
  - `tests/execution/test_ssh_provisioning.py`: 4 passed
  - `tests/test_phase6_boundaries.py`: 1 passed

---

## 10. Final Certification

OpsForge PAM V1 Phase 6 (**Target Account Provisioning**) is fully implemented, verified, and certified against all requirements in the Master Implementation Directive and Canonical Master Production Plan.

**Certification Tag**: `v1.7.0-account-provisioning`

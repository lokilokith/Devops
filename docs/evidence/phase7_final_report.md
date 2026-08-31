# OpsForge PAM V1 — Phase 7 JIT Privilege Elevation Final Report & Certification

## 1. Executive Summary

Phase 7 (**JIT Privilege Elevation — Gate 2**) implements real Just-In-Time privilege elevation for OpsForge PAM V1, building upon the certified Phase 6 baseline (`v1.7.1-account-provisioning-certified`, `9924cf55fbb432ec44b23dc7eec1a89108f17cea`).

JIT privilege elevation provides bounded, time-limited, catalog-restricted privilege elevation on Linux targets for existing active human target accounts. Privileges are granted through root-owned drop-in files in `/etc/sudoers.d/`, validated through strict `visudo` checks prior to activation, independently verified on the target over SSH, automatically expired by a background worker adhering to $\le 5$s observed overrun SLO, and recoverable across worker downtime scenarios.

**Canonical Milestone Tag**: `v1.8.0-jit-provisioning`  
**Base Certified Milestone**: `v1.7.1-account-provisioning-certified` (`9924cf55fbb432ec44b23dc7eec1a89108f17cea`)  
**Development Branch**: `phase7-development`

---

## 2. Architecture & Data Model

### 2.1 Permanent Target Abstraction: `Resource`
`Resource` remains the single permanent target abstraction representing machines and endpoints. No extraneous target entities or models were introduced.

### 2.2 Domain Models & Enums
Located in `app/jit_access/models.py`:
* **`JITGrantStatus`**: `PENDING`, `ACTIVE`, `EXPIRED`, `REVOKED`, `DENIED`, `FAILED`, `SECURITY_UNCERTAIN`.
* **`JITAccessGrant`**:
  - `id`: UUID primary key
  - `user_id`: FK `users.id` (requester)
  - `role_id`: FK `roles.id`
  - `resource_id`: FK `resources.id`
  - `target_account_binding_id`: FK `target_account_bindings.id` (links grant to active per-human target account)
  - `command_set_id`: String (bounded capability from catalog)
  - `approval_request_id`: FK `approval_requests.id`
  - `status`: `JITGrantStatus` enum
  - `activated_at`: UTC timestamp of activation
  - `expires_at`: UTC timestamp of required expiry
  - `revocation_start`: UTC timestamp when revocation began
  - `revocation_complete`: UTC timestamp when target confirmed privilege removal
  - `observed_overrun_ms`: Integer (calculated as $(t_{\text{revocation\_complete}} - t_{\text{expires\_at}})$ in milliseconds)
  - `row_version`: Integer (optimistic concurrency CAS versioning)
  - `failure_reason`: Diagnostic error details upon failure
  - `correlation_id`: Distributed tracing UUID

### 2.3 Single-Head Alembic Migration
* **Migration Script**: `migrations/versions/a1b2c3d4e5f6_add_jit_privilege_elevation.py`
* **Down Revision**: `f2a3b4c5d6e7` (Phase 6 target account bindings)
* **Single Head Confirmed**: `['a1b2c3d4e5f6']`

---

## 3. Privilege Elevation & Sudoers Lifecycle

### 3.1 Strict Administrator Capability Catalog
In adherence to zero-wildcard security invariants, commands are chosen from the administrator-defined capability catalog (`COMMAND_CATALOG` in `app/execution/helper/opsforge_helper.py`):
* `system_health_check`: `/usr/bin/uptime`, `/usr/bin/dmesg`, `/usr/bin/vmstat`
* `nginx_reload`: `/usr/bin/systemctl reload nginx`, `/usr/sbin/nginx -t`
* `view_auth_logs`: `/usr/bin/journalctl -u sshd`, `/usr/bin/tail /var/log/auth.log`
* `db_backup`: `/usr/local/bin/backup-postgres.sh`
* `container_status`: `/usr/bin/docker ps`, `/usr/bin/docker stats --no-stream`

Arbitrary commands, wildcards (`*`), and unrestricted `ALL` sudo grants are strictly rejected.

### 3.2 Target Sudoers Drop-in Sequence
Target file: `/etc/sudoers.d/opsforge-jit-<grant_id>`

The helper (`/usr/local/sbin/opsforge-helper add_jit_grant`) executes the atomic write sequence:
1. Validates `target_os_username` and `command_set_id` against catalog.
2. Formats drop-in content: `<target_os_username> ALL=(root) NOPASSWD: <command_1>, <command_2>, ...`.
3. Writes to temp file `/etc/sudoers.d/.opsforge-jit-<grant_id>.tmp`.
4. Sets permissions: `chown 0:0`, `chmod 0440`.
5. Syncs buffer: `fsync`.
6. Validates syntax: `/usr/sbin/visudo -c -f /etc/sudoers.d/.opsforge-jit-<grant_id>.tmp`. If visudo fails, the temp file is deleted and error returned immediately.
7. Atomic replace: `rename` temp file to `/etc/sudoers.d/opsforge-jit-<grant_id>`.
8. Final directory sync: `fsync`.

### 3.3 Helper Invocation Boundary
Control Plane invokes operations via SSH service account `opsforge-svc`:
* Grant Elevation:
  ```bash
  sudo -n /usr/local/sbin/opsforge-helper add_jit_grant <grant_id> <target_os_username> <command_set_id>
  ```
* Revocation:
  ```bash
  sudo -n /usr/local/sbin/opsforge-helper remove_jit_grant <grant_id>
  ```
`opsforge-svc` has bounded sudo permissions for `/usr/local/sbin/opsforge-helper` only.

---

## 4. Independent Target Verification & Failure Semantics

### 4.1 Activation Verification
Upon drop-in installation, `SSHTargetExecutor.apply_jit_grant` performs independent verification over SSH:
* Executes: `sudo -n -l -U <target_os_username>`
* Confirms target privileges match expected capability.
* Fallback: Checks drop-in file presence (`test -f /etc/sudoers.d/opsforge-jit-<grant_id>`).
* If `visudo` fails $\to$ `FAILED`.
* If network/verification uncertain $\to$ `SECURITY_UNCERTAIN` + Critical Audit alert.

### 4.2 Revocation Verification
Upon drop-in removal, `SSHTargetExecutor.revoke_jit_grant` independently tests:
* Executes: `test -f /etc/sudoers.d/opsforge-jit-<grant_id>` (must return exit code $\ne 0$, confirming file deletion).

---

## 5. Expiry Enforcement Scheduler & SLO

### 5.1 Expiry Worker (`JITExpiryWorker`)
Located in `app/workers/jit_expiry_worker.py`:
* Continuously queries active grants where `expires_at <= now`.
* Executes `service.expire_access(grant_id)` and records `revocation_start` and `revocation_complete`.
* Computes `observed_overrun_ms = revocation_complete - expires_at`.
* Enforces observed overrun SLO $\le 5$s ($5000$ms) under normal conditions.
* Emits a critical audit alert (`jit_expiry_slo_breach`) whenever the SLO is exceeded.

### 5.2 Worker-Down Crash Recovery
* Upon daemon startup, `JITExpiryWorker.run_recovery_on_startup()` runs an immediate backlog sweep of all active grants whose expiration was missed during downtime.
* Backlogged grants are revoked, verified, and logged with their computed overrun.

---

## 6. Security Controls & IDOR Protection

* **Prerequisite Active Identity**: JIT grant request strictly requires `TargetAccountBinding.status == TargetAccountBindingStatus.ACTIVE`.
* **Zero Plaintext Private Key Exposure**: Secret handling conforms to Phase 2/4/6 envelopes; in-memory release after SSH connection completion.
* **Audit Logging**: Structured events for `jit_grant.requested`, `jit_grant.activated`, `jit_grant.expired`, `jit_grant.revoked`, `jit_grant.failed`, `jit_grant.uncertain_state`, and `jit_expiry_slo_breach`.
* **Cross-User & Cross-Resource Isolation**: Validated in `tests/ownership/test_jit_ownership.py` (users cannot activate or revoke other users' grants or cross-elevate across resources).

---

## 7. Quality & Security Gate Certification

All mandatory gates passed cleanly:

| Gate | Tool / Command | Result |
| :--- | :--- | :--- |
| **Unit & Integration Tests** | `pytest` | **905 passed, 0 failed, 23 skipped** |
| **Code Coverage** | `pytest --cov=app --cov-fail-under=85` | **85.13% coverage (PASSED $\ge 85\%$)** |
| **Code Formatter** | `black --check app tests` | **PASSED (0 diffs)** |
| **Import Sorter** | `isort --check-only app tests` | **PASSED (0 diffs)** |
| **Flake8 Linter** | `flake8 app tests` | **PASSED (0 warnings/errors)** |
| **Ruff Linter** | `ruff check app tests` | **PASSED (All checks passed)** |
| **Static Type Checker** | `mypy app` | **PASSED (0 errors in 220 source files)** |
| **Security Analysis** | `bandit -r app -ll -ii` | **PASSED (0 issues identified)** |
| **Dependency Vulnerability** | `pip_audit` | **PASSED (No known vulnerabilities found)** |
| **Database Migrations** | Alembic Script Head Inspection | **PASSED (`['a1b2c3d4e5f6']`)** |

---

## 8. Phase Boundary Invariants

* **Phase 8 Boundary**: Automated failure recovery daemons and active session killer daemons remain deferred to Phase 8.
* **Phase 9 Boundary**: Full drift reconciliation engine remains deferred to Phase 9.

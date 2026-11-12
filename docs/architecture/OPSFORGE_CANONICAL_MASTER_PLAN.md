# OPSFORGE — CANONICAL MASTER PRODUCTION PLAN
## FINAL FROZEN VERSION

**Base commit:** `e58671f` (tag `v1.0.0-phase1-final`), repository `lokilokith/Devops`.
**Status:** authoritative and frozen. Future changes require an Architectural Change Request (Item 30). This document was regenerated in full for this pass — not patched — specifically to eliminate every stale cross-reference the previous version left behind, and to close the four remaining P0 gaps identified in the second review: roadmap-reference consistency, broker credential authorization, JIT expiry enforcement honesty, and the bootstrap privilege boundary. It tells one story, end to end.

**What this pass fixed, in one place:**
1. **Two genuine stale cross-references** were found and corrected: Item 9 previously said the human-account phase came "after Phase 8's bootstrap" (bootstrap is Phase 2); the bootstrap section previously said rotation and JIT were "Phase 3's rotation and Phase 4's JIT" (rotation is Phase 4, JIT is Phase 7). Every phase number in this document was checked against the canonical table in Item 22 while writing this version — there is exactly one roadmap, stated once, referenced consistently everywhere else.
2. **Broker credential authorization is now fully designed** (Item 14.1): the broker cannot simply ask Vault for "credential X." Every request is bound to session, grant, user, resource, target-account-binding, and credential IDs plus an expiry, and Vault verifies the full authorization chain before releasing anything. No generic `decrypt(credential_id)` operation exists anywhere in the system (Item 4).
3. **JIT expiry enforcement is now concrete and honest** (Item 11.2): a defined maximum overrun (Δ ≤ 5 seconds for V1), three explicit layers, measured observed-overrun as a production-certification metric, and an explicit, undisguised statement of the one residual risk this design cannot remove — the enforcement scheduler depends on the OpsForge worker being alive.
4. **A formal Bootstrap Privilege Boundary is defined** (Item 8.2): the bootstrap account no longer has direct sudo rights to write arbitrary files under `/etc/sudoers.d/` or arbitrary `authorized_keys` entries. It can invoke exactly one fixed, root-owned, fixed-path helper executable — nothing else — and account provisioning/removal are single, sequenced, verified operations on that executable (`provision_account`/`remove_account`) with a defined compensating-rollback and security-uncertainty fallback, not composable low-level steps callers assemble themselves, and not a claim of database-style atomicity over OS-level operations.
5. Bootstrap and human-target credentials are now explicitly separated into two lifecycles sharing one rotation mechanism (Item 10).
6. Target-account `REMOVED` is now an automatically triggered, verified, audited event on organizational departure — not a "someday, manually" action.
7. The full interactive shell decision for human target accounts is now justified explicitly, not merely asserted.

Everything else — the four-plane architecture, V1 scope, `Resource`-as-target decision, never-build rules, ACR mechanism, anti-drift rules — is unchanged from the prior pass.

---

## 1. Verified Current Reality

Control Plane and Vault Plane are real, tested, reproducible (539/539 tests passing live at last verification; CI enforcing lint+SAST+SCA+85%-coverage+nightly mutation testing). Execution Plane, Session Plane, production KMS, and backup/recovery design are verified absent. `Resource` already carries `hostname_ip`/`protocol`/`port` bolted directly onto the existing model — the evidence behind Item 7's target-model decision. This pass introduced no new repository findings; it corrects the plan's internal consistency and closes remaining architectural gaps, not the account of current reality.

---

## 2. Product North Star

> **OpsForge is a security-first Privileged Access Management platform that lets authorized users obtain controlled, time-bound, auditable access to privileged resources — without unnecessarily exposing the underlying privileged credentials.**

**Core workflow (V1):** request → approve → real, verified, time-bound access to a real SSH target → session brokered so the credential isn't handed to the user → expiration or revocation actually closes the session and actually removes target-side privilege → every step audited.

**Security promise:** every privileged operation OpsForge claims to have performed has actually happened on the target and been independently verified — never merely recorded.

**End-to-end chain this document must make unambiguous, in order:**

```
Identity → RBAC/Policy → Access Request → Approval → Target Account →
JIT Privilege → Brokered Session → Credential Injection → Privileged Work →
Session Enforcement → Privilege Revocation → Credential Rotation →
Verification → Audit
```

---

## 3. Product Boundary

OpsForge is **not** a password manager, a generic secrets manager, an IAM replacement, a security dashboard, a CRUD application, or a collection of database state machines.

OpsForge **is** a security-first PAM platform that uses identity, policy, protected credentials, target-side execution, JIT privilege elevation, brokered sessions, revocation, rotation, and audit to control real privileged access to real systems. The project is not complete when database state changes — it is complete when the target itself reflects that state and OpsForge has verified it.

---

## 4. Four-Plane Architecture

**Control Plane** — identity, RBAC, policy, access requests, approvals, the JIT *decision*, target-approval workflow.
**Vault Plane** — envelope-encrypted storage, versioning/CAS, production KMS, rotation policy, credential-lease state, key/decryption authority, and the **authorized credential-use operation** (below).
**Execution Plane** — the only component with outbound network access to privileged targets.
**Session Plane** — the only component holding a live, user-facing privileged connection.

### Process/trust-boundary model

**Decision: modular monolith, split across at least two OS processes — a web/API process and a worker process.**

```
WEB/API PROCESS                         WORKER PROCESS
  ├── Control Plane                       ├── Execution Plane
  └── Vault Plane                         └── Session Plane
       └── human credential
           reveal capability
           (existing, audited)

              X ── plaintext ── X
     (prohibited in both directions, always)
```

- The web/API process never initiates outbound connections to privileged targets.
- The worker process is the only process with outbound network access to targets. It independently retrieves and decrypts the specific credential it needs, in its own process, through the Vault library, using its own authorized KMS access.
- **The web process cannot instruct the worker by sending it plaintext, and the worker cannot request an arbitrary credential.** There is no channel across which plaintext travels between the two processes, under any circumstance.
- **No generic `decrypt(credential_id)` operation exists anywhere in the codebase.** Vault Plane exposes only a narrow, authorized **credential-use operation**, whose exact required inputs are defined in Item 14.1 (the same operation the broker calls, and the only decrypt-shaped call in the system, so there is exactly one place, not several, where the authorization chain is enforced). Rotation and JIT provisioning inside Execution Plane call the same narrow pattern — a specific, already-authorized operation, never a bare credential lookup by ID.
- Isolating Execution Plane into its own container/host later is a deployment change, not an architecture change. Introducing a network hop between a caller and Vault's credential-use operation, where none exists today, requires an ACR.

---

## 5. Trust Boundaries

Four independent trust decisions govern every operation against a target:

1. **Network trust.** Outbound connections are restricted to explicitly allowlisted target address/port ranges captured at registration. The address is **resolved once, validated against the allowlist and against blocked ranges (RFC1918/link-local/metadata-service), and the connection is made directly to that validated address** — never re-resolving the hostname before connecting, which would reopen the DNS-rebinding race. `internal=true` on a target registration does **not** disable SSRF checking; it means "an administrator has explicitly authorized this target to reside inside an approved internal network boundary," and the address is still validated, pinned, and logged as an elevated-trust registration requiring its own approval step.
2. **Host identity trust.** SSH host key is pinned at registration (trust-on-first-use requires explicit administrator confirmation), stored, and re-verified on every connection. A mismatch is a hard failure, alerted, never silently accepted.
3. **Administrative trust.** A registered target is unusable until it passes the existing approval-workflow module as a distinct target-approval step.
4. **Credential trust.** An explicit credential↔target↔account binding is checked before every operation.

---

## 6. Credential/Secret Lifecycle

> **Vault Plane owns all key/decryption authority. No other component ever receives a persistent decryption key.** Execution Plane and Session Plane may each receive only the minimum ephemeral credential *material* required for one specific, already-authorized operation, released only through the narrow credential-use operation (Items 4, 14.1), passed as a same-process call argument, and never returned, cached, logged, or persisted.

**Honest memory claim (kept from the prior pass — this was correct and does not change):** this document makes no promise that Python plaintext values are "zeroed" or reliably overwritten in memory — that is not a guarantee the language provides. The actual invariant is:

> **Minimize plaintext exposure, and make every plaintext-bearing boundary explicit and auditable.**

Concretely: minimize plaintext lifetime and the number of copies made of it; never persist it to disk, database, cache, or log; never place it in an exception message; never serialize it onto a queue; never retain it in session/request state beyond the single call that needs it; never return it from a function signature typed as plaintext beyond the immediate call; never expose it through any API response.

Enforcement remains automated log-scraping tests on every plaintext-touching code path, run from the moment Execution Plane first touches plaintext (Phase 3) onward.

---

## 7. Target Model

`Resource` remains the permanent target abstraction, extended in place — evidenced by the existing `hostname_ip`/`protocol`/`port` columns already on the model. No separate `Target` model in V1.

Fields, added incrementally per phase: identity/address (exists); host identity (Phase 3); administrative trust / target-approval status (Phase 3); capabilities (`can_rotate`, `can_jit`); credential bindings (a join table, Phase 4); lifecycle (reuses existing `ResourceStatus`).

---

## 8. Target Bootstrap Model

Bootstrap is Phase 2 — it precedes every capability that depends on OpsForge already having a target-side identity (the SSH Executor, Phase 3; rotation, Phase 4; JIT, Phase 7). Nothing in this document authenticates to a target before Phase 2 has run.

### 8.1 — Bootstrap identity

Each target's onboarding runbook (a human, out-of-band step, not automated by OpsForge in V1) provisions a dedicated, non-human OS account, `opsforge-svc`, with:

- **Authentication:** SSH key-based only, password authentication disabled.
- **Storage:** the bootstrap private key is generated at onboarding and immediately imported into Vault Plane (KMS-wrapped); it never persists on disk outside the target and the vault.
- **Rotation:** covered in Item 10.1 — the bootstrap credential is rotation-managed, and is the very first credential the rotation mechanism ever rotates (Phase 4).
- **The genuine chicken-and-egg:** the very first bootstrap key for a newly onboarded target cannot be provisioned by OpsForge, since OpsForge has no privilege on that target yet. This is accepted as a documented, manual, out-of-band onboarding step.
- **Emergency recovery:** a lost/compromised bootstrap credential is recovered the same way it was created — manual, out-of-band re-provisioning — followed by a mandatory reconciliation sweep (Item 12) before automation resumes against that target.

### 8.2 — Bootstrap Privilege Boundary (new — closes the remaining gap)

Saying `opsforge-svc`'s privilege is "narrowly scoped" is not itself a security boundary — it has to be structurally impossible for the account to exceed that scope, not merely undesired. This document now defines the boundary structurally, not by assertion.

**Decision: `opsforge-svc` does not have direct sudo rights to write files. It has sudo rights to execute exactly one fixed, root-owned, fixed-path helper executable, and nothing else.**

```
opsforge-svc
    ↓ sudo, restricted to exactly one command
/usr/local/sbin/opsforge-helper   (root:root, mode 0750, executable only by
                                    the opsforge-svc account/group, immutable
                                    once deployed — content changes go through
                                    the target's own configuration-management
                                    channel, not through OpsForge itself)
    ↓ a root-owned, fixed-path executable — not a shell script — so there is
      no shell expansion, environment-variable substitution, IFS/quoting
      behavior, or PATH-dependent resolution to reason about; caller-supplied
      values are never passed to a shell, ever
    ↓ takes strictly validated, positional arguments
    ↓ performs exactly one of a fixed, allowlisted set of operations:
      - provision_account <account> <public_key>   (single sequenced operation:
        create-or-verify the account, install the key, record ownership,
        verify — Item 9)
      - remove_account    <account>                (single sequenced operation:
        revoke key, disable/remove account, verify — Item 15)
      - add_jit_grant      <grant_id> <account> <allowlisted-command-set-id>
      - remove_jit_grant   <grant_id>
```

**Why account provisioning is one sequenced, self-contained operation, not separate create/install-key steps callers compose:** a two-step `create_account` + `add_account_key` interface can fail between the steps and leave an orphaned, keyless account with nothing responsible for noticing. `provision_account` performs the complete sequence server-side so no caller ever needs to compose the steps itself — but this document does not claim that `useradd` + a filesystem write + a manifest update can be made atomic in the database-transaction (ACID) sense, because they can't be: they're separate OS-level operations, not one commit. The honest model is:

```
preconditions checked → perform each step in order → on any failure, run the
step's own compensating rollback (undo what that step did, best-effort) →
verify the resulting target state → report either success, or an explicit
failure/security-uncertainty state (Item 13) — never a false "success"
```

1. Validate `<account>` against the strict POSIX-safe naming policy (Item 9's deterministic derivation) — reject anything else.
2. If the account already exists, this is only valid as an explicitly defined idempotent reconciliation case (Item 12) — otherwise reject.
3. Create the account using fixed, server-side parameters — **the caller never supplies a UID or GID**.
4. Configure the account with the V1-approved shell (Item 9's justified `/bin/bash` decision).
5. Lock/disable password authentication for the account.
6. Install the supplied public key into `authorized_keys`.
7. Ensure the account receives no groups or privileges beyond the fixed default — never whatever the caller might imply.
8. Record the account as OpsForge-owned in the protected local manifest (below) — this is the *only* way an account becomes eligible for any later helper operation against it.
9. **Verify** the resulting account and key state by direct inspection (not by trusting step 3–8's return codes alone).
10. Return success only after step 9's verification. **If any step from 3 onward fails, the helper attempts a compensating rollback of whatever partial state the earlier steps left** (e.g., delete the partially created account) **and then re-verifies** — if that rollback itself cannot be confirmed to have fully succeeded, the operation reports a security-uncertainty state (Item 13), not a plain failure, since the target's actual state is no longer confidently known. This is a bounded, tested, best-effort guarantee, not a database-style atomic transaction — and Phase 6/7's test suite (Item 23) is required to deliberately kill the helper mid-sequence to exercise this rollback-and-verify path, not just the happy path.

`remove_account` follows the same honest model: confirm the account is manifest-recorded as OpsForge-owned (refusing `root` and any unrecorded/system account outright); remove its SSH credential; remove any remaining JIT privilege for it; disable/remove the account per the V1 lifecycle policy (Item 15); verify the final state directly; report success only after that verification, or a security-uncertainty state if an interruption leaves the resulting state unclear.

**The target-local ownership manifest — hardened, not merely mentioned:** the file the helper consults to decide which accounts it's allowed to touch is itself a security boundary, not an implementation detail. It is `root:root`, mode `0600`, and **the helper is its only writer** — `opsforge-svc` never has direct write access to it, exactly as it never has direct write access to `/etc/sudoers.d/` or `authorized_keys`. Entries are added or removed only as a side effect of a successful `provision_account`/`remove_account` call — there is no "set manifest entry" operation that accepts arbitrary caller-supplied data, and no path by which a caller could declare `root` or any other account OpsForge-owned. An account is eligible for `add_jit_grant`, `remove_jit_grant`, or `remove_account` only if the manifest already records it — recorded there only by a prior successful `provision_account`.

The helper, not `opsforge-svc` directly, is the only thing on the target that ever writes to `/etc/sudoers.d/`, edits an `authorized_keys` file, or touches the manifest. Its allowlisted operations enforce, by construction:

- It can write **only** to `/etc/sudoers.d/opsforge-jit-*` — never to `/etc/sudoers` or any other file under `/etc/sudoers.d/`. There is no code path in the helper that accepts an arbitrary filename.
- It can edit `authorized_keys` **only** for accounts the manifest records as OpsForge-owned — it categorically refuses `root`'s keys or any account not in the manifest.
- Every sudoers entry it writes goes through the write sequence in Item 11.1 — **validated before it is ever made active**, not after — the helper is where that sequence is implemented, not a suggestion layered on top of a more permissive account.
- It performs no shell interpolation of any argument, ever; arguments are parsed positionally and validated against a strict schema before any file operation is attempted; an invalid argument is rejected with no side effect.
- It logs every invocation (operation, arguments, caller, result) to the target's own system log, independent of and in addition to OpsForge's own audit trail — a second, target-local record that doesn't depend on OpsForge's own logging pipeline being intact.

**The security property this achieves:** `opsforge-svc` cannot modify `root`'s SSH keys, cannot grant itself unrestricted sudo, cannot write an arbitrary executable as root, and cannot touch any sudoers file outside its own namespace — because none of those actions correspond to any operation the helper exposes, not because a policy document asks it not to. If a genuinely new target-administration capability is needed later, it is added as a new allowlisted helper operation through an ACR, reviewed for exactly this boundary — never by broadening `opsforge-svc`'s own sudo rights.

---

## 9. Target Account Provisioning — human ↔ target identity

**Trigger:** the first approved access request for a given (Control Plane user, target `Resource`) pair with no existing binding. Accounts are provisioned lazily, on first need.

**Mapping:** `target_account_bindings` — `control_plane_user_id`, `resource_id`, `target_os_username`, `ssh_credential_id`, `status` (Item 15). Invariants, all enforced at the application layer:

1. One Control Plane user has at most one target account per target (unique on `(control_plane_user_id, resource_id)`).
2. Two Control Plane users never share an OS account, on any target, ever.
3. An OS account is never used by OpsForge unless its binding is `ACTIVE`.
4. A `SUSPENDED` user cannot create a new session or JIT grant (Item 15).
5. A `REMOVED` user cannot authenticate through OpsForge in any capacity.

**Username derivation:** a deterministic slug from the user's existing Control Plane identity, with a numeric suffix appended only on collision — computed once at first provisioning and stored in the binding row.

**Who creates it, and how:** Execution Plane, authenticating as the bootstrap identity, invokes the helper's single `provision_account` operation (Item 8.2) with the derived username and a public key generated inside Vault Plane (private half never leaving the vault). The helper — not raw `opsforge-svc` sudo rights, and not a caller-composed sequence of lower-level steps — performs account creation, key installation, and manifest registration as one sequenced, self-verifying operation with a defined compensating rollback if an intermediate step fails (Item 8.2), which is what keeps an orphaned, keyless account from surviving undetected — not a claim that the underlying OS operations are atomic in the database-transaction sense.

**Shell decision, justified (previously asserted without justification):** the account's login shell is a standard interactive shell (`/bin/bash`), not a restricted shell. This is deliberate, not an oversight: the entire point of a brokered session (Item 14) is to deliver the user *real, unrestricted work capability* on the target once authorized — that's the product. Restricting the shell would break the core use case the broker exists to serve. The mitigation is not a restricted shell; it's that the account carries **no standing privilege beyond ordinary unprivileged access** until a JIT grant (Item 11) is active, and every path to that account — key material, session establishment, privilege elevation — is independently gated by the mechanisms in Items 9, 11, and 14. Shell restriction was considered and rejected as redundant with those controls, and as directly conflicting with the product's purpose.

**Verification:** before the binding is marked `ACTIVE`, Execution Plane opens a fresh authenticated connection using only the new key and confirms success.

**What happens if the OS account is missing when expected:** a pre-flight check runs immediately before every JIT-provisioning or session-start request, failing closed with a clear error if the account is absent; the reconciliation sweep (Item 12) catches it as a backstop on its regular schedule.

Full lifecycle (`PENDING → ACTIVE → SUSPENDED → REMOVED`), including exactly what triggers `REMOVED` and what it does, is defined in Item 15.

---

## 10. Credential Rotation — two lifecycles, one mechanism

The prior pass treated the bootstrap credential and human target-account credentials as one undifferentiated rotation target. They share a mechanism but not a policy: a failed bootstrap rotation risks OpsForge's own administrative foothold on a target; a failed human-account rotation affects exactly one user's account. This pass separates them explicitly.

**Shared mechanism — SSH keypair rotation (Ed25519), add-then-verify-then-remove, atomic writes throughout:**

1. Generate a new keypair in Vault Plane (KMS-wrapped).
2. Add the new public key to the target account's `authorized_keys` alongside the existing key — atomic write (temp file → owner/mode → fsync → atomic rename, refusing to follow a symlink).
3. Open a fresh connection authenticating with *only* the new private key and confirm it works.
4. Only after step 3 succeeds, remove the old key via the same atomic-write discipline.
5. Update Vault's current-credential pointer only after step 4 confirms the target reflects only the new key.

### 10.1 — Bootstrap Credential Lifecycle

- **What it protects:** OpsForge's own administrative foothold on the target (Item 8).
- **First rotated:** Phase 4 — the very first rotation OpsForge ever performs is against its own bootstrap key, proving the mechanism on the credential the rest of the system depends on.
- **Failure severity:** highest in the rotation category. A failed bootstrap rotation is treated as a security-uncertainty-adjacent finding (Item 13) even when the target state is technically known (old key still valid), because it puts the *next* rotation, JIT operation, or account-provisioning action against that target at risk if not resolved promptly.
- **Recovery:** verification failure (step 3) → `ROTATION_FAILED`, old key remains valid, retried on the normal rotation schedule. Old-key-removal failure (step 4) after step 3 succeeded → `DESYNCED`, escalated for prompt manual attention given the account's administrative role, rather than left to the ordinary reconciliation cadence.
- **Audit:** every bootstrap rotation event is a distinct, elevated-severity audit category from a human-account rotation event, even though the underlying code path is shared.

### 10.2 — Human Target Credential Lifecycle

- **What it protects:** a single (user, target) `target_account_bindings` row (Item 9).
- **Failure severity:** standard `ROTATION_FAILED`/`DESYNCED` severity — affects one user's access to one target, not OpsForge's administrative capability.
- **Recovery:** identical mechanism (add-then-verify-then-remove), same failure states, standard alerting rather than elevated.
- **Interaction with account removal:** a `REMOVED` binding (Item 15) revokes this credential outright rather than rotating it — rotation only applies to an `ACTIVE` binding.

---

## 11. JIT Privilege Elevation Model

```
Control Plane user
       ↓
Target account (permanent — Item 9)
       ↓
SSH authentication (permanent key — Item 9/10.2)
       ↓
JIT sudo privilege (temporary — this section)
       ↓
Privileged operation
```

This is **privilege elevation for an existing target identity** — the mechanism never creates identity; Item 9 already did that.

### 11.1 — Mechanism, via the bootstrap helper (Item 8.2)

A per-grant `/etc/sudoers.d/opsforge-jit-<grant_id>` drop-in file. `grant_id` is a UUID, so the filename can never contain a path-traversal or shell-injection-relevant character. Provisioning and revocation are performed **exclusively through the helper's `add_jit_grant`/`remove_jit_grant` operations** (Item 8.2) — `opsforge-svc` never writes this file directly.

The helper's internal write procedure, exact and ordered:

1. **Generate** the file's content from a strict, enumerated allow-list template (Item 11.3) — never freeform string interpolation of a command a requester supplied. The requester chooses from an administrator-defined capability set; nothing resembling "sudo command = arbitrary string" reaches the template.
2. **Validate** the generated content against the template schema before touching the filesystem.
3. **Write to a temp file** in the same directory, refusing to proceed if `/etc/sudoers.d` itself is anything other than root-owned and non-world-writable.
4. **Set owner/mode on the temp file:** `root:root`, `0440`.
5. **`fsync`** the temp file.
6. **`visudo -c -f <temp file>`** — validate the *temporary* file, before it can ever become active. **An unvalidated sudoers file must never become active — this is a hard invariant, not a preference.** If validation fails, the temp file is deleted and nothing is installed; the live `/etc/sudoers.d/` directory is never touched.
7. **Only if validation succeeds, atomically rename** the validated temp file to its final path, refusing if the final path is a symlink.
8. **`fsync` the containing directory** after the rename, so the install itself is durable.
9. **Live verification:** `sudo -l -U <target_os_username>` confirms the expected grant is visible.
10. **Cleanup on any failure** at steps 1–9: temp file removed, no partial state left in `/etc/sudoers.d`.

Revocation runs the same discipline in reverse (delete-if-present via `remove_jit_grant`, verify absence via `sudo -l`).

### 11.2 — JIT expiry enforcement — concrete bound, honest limitation

**V1 operational enforcement SLO:** under healthy-worker operating conditions, target-side JIT privilege removal must complete within a maximum observed enforcement window of **Δ ≤ 5 seconds** after authorization expiry, unless a specific target's technical constraints require documenting a different value for that target (an explicit exception, not a silent default change). This is stated as an SLO, not an absolute guarantee — "healthy-worker conditions" is doing real work in that sentence, and the paragraph below defines what happens outside it.

Three explicit layers, not one mechanism wearing three names:

```
Layer 1 — Normal scheduled revocation
   A dedicated expiry-enforcement scheduler (independent of, and running at a
   materially tighter interval than, the general reconciliation sweep) checks
   every grant's expires_at (UTC) against the current time and immediately
   invokes the Item 11.1 revocation sequence for anything past expiry.
        ↓
Layer 2 — Target-side bounded enforcement
   Layer 1's revocation call is itself the target-side enforcement — there is
   no separate always-on target-resident agent in V1 (one was evaluated and
   rejected, Item 18/never-build). This means Layer 2, as implemented in V1,
   is not independent of the OpsForge worker process being alive; that
   dependency is stated plainly in the paragraph below, not hidden behind
   the phrase "bounded enforcement."
        ↓
Layer 3 — Reconciliation / recovery
   If Layer 1 misses an expiry (target unreachable at the moment of check,
   or the worker itself was down), reconciliation (Item 12) detects the
   surviving grant on its own schedule once the worker is back and completes
   the revocation as a safe deterministic retry (Item 12) — completing an
   already-decided action, not making a new one.
```

**The one residual risk this design does not remove, stated explicitly rather than disguised as "bounded, measured overrun":** if the OpsForge worker process is dead for longer than a grant's remaining lifetime, no layer in this design removes that grant's target-side privilege until the worker (or a replacement instance of it) is running again and either Layer 1 catches up or Layer 3's reconciliation runs. **Worker unavailability is classified as a security-uncertainty / recovery condition (Item 13), not a variant of the 5-second SLO** — reconciliation and manual recovery are the backstop for it, and this document never claims the SLO holds under total system failure. This is an accepted V1 limitation, not a claim of independence from OpsForge's own availability. A target-resident privileged agent would remove this dependency but was rejected for V1 (introduces a persistent, privileged piece of software on every target, conflicting with this architecture's no-agent design) — revisiting that tradeoff is an ACR, informed by the observed-overrun measurements below.

**Measurement, required from Phase 7 onward and mandatory at production certification (Item 27):** every grant records `expiry_time`, `revocation_start`, `revocation_complete`, and the computed `observed_overrun`. **Production certification requires demonstrating that observed overrun remains within the declared bound (Δ ≤ 5 seconds) under normal operating conditions** — not merely that the mechanism exists.

If Δ is exceeded on a given grant: the grant's state becomes a security-uncertainty finding (Item 13), a P0 alert fires immediately (not deferred to the next reconciliation cycle), and the response assumes the associated session (if any) is already closed via Layer 1 of Item 14.2 independent of whether target privilege removal itself succeeded on time.

### 11.3 — Privilege-conflict / concurrency model

Overlapping grants against the same target account are permitted; the risk of two individually-valid grants combining into excessive privilege is resolved at the **policy layer**:

> **V1's policy templates never permit a wildcard command grant** (e.g., `sudo systemctl restart *`, `ALL=(ALL) NOPASSWD: ALL`) **unless a specific grant is explicitly reviewed and proven safe by an administrator as a documented exception** — never as a default. Every grant's command allow-list is an explicit, enumerated set, validated against the policy engine's schema at approval time. Two narrow, enumerated grants combining can only produce the union of two explicit lists — a bounded, reviewable set, never an emergent, unbounded privilege.

---

## 12. Reconciliation Model

```
detect → classify → alert → retry if safe → manual intervention if uncertain → verify → resolve
```

- **Safe deterministic retry** — the mismatch is an already-authorized action that didn't finish (e.g., a grant is `expired` in OpsForge's state but its sudoers file is still present, per Item 11.2's Layer 3 — completing Item 11.1's revocation is not a new decision, it's finishing one already made). Retried automatically, logged, alerted only if the retry itself fails.
- **Manual intervention required** — no already-authorized action exists to complete (e.g., a sudoers file matching `opsforge-jit-*` with a `grant_id` reconciliation has no record of at all — possibly a legitimate emergency out-of-band action, possibly a compromise; OpsForge cannot tell which, so it never auto-deletes it).

V1 minimum scope: JIT-grant state and rotation-credential state. Each finding carries severity, an audit event, an operator action, a retry policy, and a final resolution state — never left open-ended.

---

## 13. Failure Model

`DESYNCED`, `PROVISIONING_FAILED`, `REVOCATION_FAILED`, `ROTATION_FAILED`, `SESSION_TERMINATION_FAILED` — each carrying reason/timestamp/actor/retry-behavior/visibility/alerting/recovery-procedure/audit-event. Operation failure (known target state) is distinguished from security uncertainty (target state cannot be confidently determined) — security uncertainty is strictly higher severity and feeds directly into Item 11.2's Δ-exceeded alerting and Item 12's reconciliation classification. The architecture never claims that a database flag alone terminates a real session or removes real privilege — every one of these states exists specifically because that claim would be false.

---

## 14. Session Model

### 14.1 — Broker credential authorization (fully specified — closes the remaining gap)

The full chain, with the authorization step now explicit rather than assumed:

```
User
 ↓
Control Plane authorization (existing JWT auth)
 ↓
Approved access grant (existing access-request/approval workflow)
 ↓
Session authorization (a session-specific grant, tied to the JIT grant, Item 11)
 ↓
Broker
 ↓
Credential-use authorization request  ◄── this step, previously assumed, is now defined
 ↓
Vault (verifies the full chain below before releasing anything)
 ↓
Ephemeral private key material, released only for this one operation
 ↓
SSH connection to the target account (Item 9)
```

**The broker never simply asks Vault for "credential X."** Every credential-use request the broker makes is bound to, and Vault verifies, all of the following before releasing anything:

```
session_id
grant_id
user_id
resource_id
target_account_binding_id
credential_id
requested_at
expires_at
```

Vault checks that: the session is currently authorized and unexpired; the grant it derives from is currently `ACTIVE` (Item 11); the user's `target_account_bindings` row (Item 9) for this resource is `ACTIVE`, not `SUSPENDED` or `REMOVED` (Item 15); the credential ID matches the one actually bound to that binding; and the request arrives before `expires_at`. **If any check fails, Vault denies the request — the broker fails closed.** This is the same narrow "credential-use operation" referenced in Item 4; it is the only decrypt-shaped call in the system, and this is the one place its full authorization contract is defined.

The released credential material: never persisted by the broker, never logged, never returned to the user, never placed on a queue, never included in session metadata, never cached beyond the immediate connection-establishment operation.

**The broker ADR (Gate 3) may propose changes to this chain's implementation** if concrete evidence demonstrates the current model is unsafe or technically incompatible with the chosen broker technology — such a change requires an ACR documenting the evidence, the proposed change, and its security impact. It may not silently redesign the chain, and it may not weaken the authorization-binding list above.

### 14.2 — Session termination — two independent layers, honestly bounded

> **OpsForge must have a bounded, testable mechanism for preventing continued privileged use after authorization expiry or revocation.** This is not a claim that any single layer is instantaneous or unconditional.

- **Layer 1 — broker/session-level enforcement (best-effort, fast).** On expiry or admin-revoke, Session Plane attempts to force-close the live socket immediately.
- **Layer 2 — target-level enforcement (Item 11.2), independent of the broker's own health, though not of the OpsForge worker's.** The expiry-enforcement scheduler pulls the underlying sudo privilege at the target on its own schedule, regardless of whether the broker successfully closed the socket. If the broker itself has crashed or been compromised, this layer is what still bounds actual exposure — subject to the Item 11.2 residual-risk statement about the worker process's own availability.
- **Backstop — hard maximum session TTL** (an absolute cap independent of any extension mechanism), defined at Phase 12, providing a bound even if neither layer's normal triggering path fires as expected.

**Termination ordering:**

1. Layer 1 attempts socket closure immediately, best-effort.
2. Execution Plane attempts target-side privilege revocation (Item 11.1) as a separate, independently tracked operation — not gated on Layer 1's success.
3. Verification confirms the sudoers file is gone and `sudo -l` no longer reflects the grant; only then is the grant marked `REVOKED`.
4. If step 2 or 3 fails, `REVOCATION_FAILED` (Item 13), regardless of whether Layer 1 succeeded.
5. If Layer 1 itself fails (socket won't close, broker unresponsive) — the single most severe failure state in the system, escalated above `REVOCATION_FAILED`, paging immediately. Item 11.2's Layer 2 is what bounds actual damage while that page is being responded to, within its own stated residual-risk limits.

The residual-risk model is stated once, plainly, in Item 11.2, and applies here without restatement: a compromised or crashed broker does not imply indefinite privileged access, but a simultaneously-dead OpsForge worker process is a real, undisguised limitation of V1's design, not a scenario this document claims to have solved.

---

## 15. User / Target-Account Lifecycle

```
PENDING → ACTIVE → SUSPENDED → REMOVED
```

- **PENDING** — binding requested/approved, account creation and verification (Item 9) not yet complete.
- **ACTIVE** — account exists, verified, usable for JIT and session requests.
- **SUSPENDED** — entered **automatically and immediately** the instant the corresponding Control Plane user is deactivated/disabled, or an administrator suspends the binding directly. This cascades immediately: any active JIT grant for this binding is revoked through the normal Item 11 sequence; any active session is terminated through Item 14.2's sequence; new JIT/session requests against this binding are refused. The target OS account and its key are **not** deleted in this state, preserving the account for audit/forensic purposes.
- **REMOVED** — triggered **automatically** by the distinct Control-Plane event "user removed from the organization" (not the same event as deactivation, which only produces `SUSPENDED`). On this event, OpsForge automatically, without waiting for a separate manual step:
  1. Revokes all remaining target privileges for this binding (Item 11).
  2. Terminates all sessions for this binding (Item 14.2).
  3. Invokes the helper's `remove_account` operation (Item 8.2) — which itself confirms manifest ownership, revokes the SSH credential, removes any remaining JIT grant, disables/removes the account, and verifies the result, with a security-uncertainty fallback (not a false success) if verification cannot confirm the outcome — rather than composing separate key-removal and account-removal steps.
  4. **Verifies** target state — confirms the key/account is actually gone or disabled, not merely that the removal command was issued.
  5. Records the complete operation, including the verification result, in audit.
  Failure at step 3 or 4 produces a security-uncertainty state and an operational alert — it does not silently leave an orphaned, still-privileged target account. Every `target_account_bindings` row that reaches `REMOVED` has a verified target-side outcome, not an assumed one; reconciliation (Item 12) additionally sweeps for orphaned OpsForge-owned target accounts with no corresponding `ACTIVE`/`SUSPENDED` binding, as a backstop.

Two Control Plane users never map to the same OS account (Item 9's uniqueness constraint). A binding whose OS account is missing when expected fails closed at request time and is caught by reconciliation as a backstop.

---

## 16. Non-Negotiable Security Invariants

1. Database state is never proof of target-side success.
2. A privileged session's exposure is bounded by two independent enforcement layers (Item 14.2), with the one residual worker-availability dependency stated plainly, not disguised (Item 11.2).
3. Plaintext credentials never cross a process boundary; they exist only inside the single process invocation that needs them, released only through the narrow credential-use operation (Items 4, 6, 14.1) — there is no generic decrypt-by-ID call anywhere in the system.
4. Failure states are first-class; security-uncertainty states are strictly higher severity than known-outcome operation failures.
5. `LocalEnvironmentKeyProvider` must never be reachable in a production deployment holding real privileged credentials.
6. No production release without real KMS.
7. Every new object type gets the same object-level authorization test coverage already proven for access requests and notifications.
8. Frontend does not lead the project.
9. Every target-mutating operation is idempotent by construction.
10. Authorization decisions are evaluated on UTC wall-clock time; scheduling loops use monotonic time for their own internal robustness; target-reported time is never authoritative.
11. Bootstrap/secret-zero credentials are scope-limited (Item 8.2's helper boundary) and rotation-managed (Item 10.1) like any other credential.
12. JIT grants never carry a wildcard command allowance by default (Item 11.3).
13. No production-like privileged credential is used with the local/dev KMS provider from Phase 4 onward.
14. **`opsforge-svc` never has direct filesystem write access to `/etc/sudoers.d/` or any `authorized_keys` file — all such writes go through the single allowlisted helper (Item 8.2).**
15. **Every credential-use request is bound to session, grant, user, resource, target-account-binding, and credential IDs plus an expiry, verified in full before release (Item 14.1); an unbound or partially-bound request is always denied.**

---

## 17. V1 Scope

```
Identity + Authentication + RBAC + Policy + Vault           (exists, hardened)
+ SSH target registration + validation (four trust boundaries, corrected SSRF model)
+ Target bootstrap identity, restricted to one allowlisted helper (Phase 2)
+ Real, verified SSH keypair rotation — bootstrap first, then per-human accounts,
  as two distinct lifecycles sharing one mechanism
+ Target account provisioning: per-human, per-target OS identity, with its own
  lifecycle including automatic, verified removal on departure
+ Real JIT privilege elevation via sudoers.d (through the helper), with active
  target-enforced expiry, a declared maximum overrun bound, and measured evidence
+ Session Broker (build-vs-buy ADR, hard gate, may challenge the identity model
  and credential-authorization chain with evidence via ACR)
+ Brokered SSH sessions with a fully specified, bound credential-use authorization
+ Two-layer session termination enforcement, with the worker-availability
  dependency stated explicitly rather than hidden
+ Reconciliation with safe-retry vs. manual-intervention classification
+ Audit extended across all four planes
+ One production KMS provider, contract-validated from Phase 1, barred from
  production-like credentials from Phase 4 onward
+ Observability, incl. wall-clock/monotonic time separation and overrun measurement
+ Backup/recovery, incl. a real tested restore + post-restore reconciliation dry-run
+ Security testing against the full matrix plus an adversarial pass
+ Reproducible disposable test-target environment with fault injection
```

---

## 18. Explicitly Deferred Scope

PostgreSQL (non-blocking, parallel validation phase); break-glass/emergency access (fully deferred — see below); multi-tenancy, session recording, multiple KMS providers, non-SSH protocols, Kubernetes/cloud-IAM integrations, HA/multi-region, mobile apps, secrets-as-a-product, cosmetic frontend work ahead of operational necessity; temporary SSH users/keys as a JIT mechanism; a target-side privileged expiry-enforcement agent (Item 11.2 — considered and rejected in favor of the scheduler-based bounded-window approach with its stated residual risk); a real-time privilege-aggregation/conflict-detection engine (resolved at the policy layer instead, Item 11.3).

**Break-glass, explicit V1 decision:** deferred unless required for the minimum production operational model. No special break-glass workflow exists in V1. Emergency recovery is an operational/manual procedure — direct, out-of-band administrator action on the target, not mediated by OpsForge — which must still be auditable and is reconciled afterward via Item 12's sweep. This document does not accidentally create an informal break-glass path anywhere else in its design (in particular, Item 8.2's helper exposes no "emergency override" operation). A future in-product break-glass implementation requires an ACR.

---

## 19. Never-Build Rules

Multi-tenancy; RDP or any non-SSH/non-Postgres protocol before SSH V1 certifies; Kubernetes access management; cloud IAM integrations; secrets-management-as-a-product; session recording; a mobile application; break-glass as an in-product feature (Item 18); third-party integrations unrelated to PAM; additional target protocols before SSH V1 certifies; multiple KMS providers; HA/multi-region before single-node production is proven; cosmetic frontend redesign ahead of operational/security workflow completeness; speculative abstraction layers not required by an already-scheduled phase; temporary SSH users or keys as a JIT mechanism; a target-side privileged agent for expiry enforcement; wildcard/wide-scope sudoers grants as a default; a real-time privilege-aggregation engine; a separate `Target` model; a network service boundary between Vault Plane and its callers without an ACR; **any direct filesystem-write sudo grant to `opsforge-svc` outside the single allowlisted helper (Item 8.2)**; **any credential-release code path that does not require the full binding set in Item 14.1**.

**Frontend priority order:** operational correctness → security-state visibility → error visibility → target management → JIT workflow → session workflow → rotation workflow → audit → cosmetic improvements last. Incremental operational UI ships alongside backend capability (rotation state/DESYNCED visibility once rotation exists; JIT request/approval/provisioning/expiry/revocation once JIT exists; session status/termination once sessions exist) — not deferred wholesale to the final phase, which handles only consolidation and usability polish.

---

## 20. Dependency Graph

```
VERIFIED FOUNDATION (Control + Vault Plane)
        ↓
PHASE 0  — Stabilization
        ↓
PHASE 1  — Architecture Contract (minimal interfaces + KMS contract)
        ↓
PHASE 2  — Target Bootstrap + Disposable SSH Test Environment
            (opsforge-svc + the single allowlisted helper, Item 8)
        ↓
PHASE 3  — SSH Executor (connect using bootstrap identity, four trust boundaries,
            corrected SSRF model)
        ↓
PHASE 4  — Real SSH Rotation (bootstrap account's own key, first — Item 10.1)
        ↓                                                    ◄── first genuine PAM capability
PHASE 5  — Rotation Engine / Scheduler (unattended, idempotent)
        │
        │        ┌── PHASE 5-PARALLEL — PostgreSQL Executor
        │        │   NON-V1 / PARALLEL ARCHITECTURAL VALIDATION
        │        └──
        ↓
PHASE 6  — Target Account Provisioning (human↔target OS identity, Item 9,
            using the bootstrap helper's account/key operations)
        ↓
PHASE 7  — JIT Privilege Elevation (Item 11: helper-mediated sudoers.d, hardened
            write sequence, active target-enforced expiry with measured overrun)
        ↓
PHASE 8  — JIT Revocation / Failure Recovery
        ↓
PHASE 9  — Reconciliation (safe-retry vs. manual-intervention classification)
        ↓
PHASE 10 — Session Broker Architecture Decision  ◄── HARD GATE, ADR may challenge
            the identity/authorization chain with evidence via ACR
        ↓
PHASE 11 — Brokered SSH Session (Item 14.1's fully specified credential authorization)
        ↓
PHASE 12 — Credential Injection + Session Control (two-layer termination, hard session TTL)
        ↓
PHASE 13 — Production KMS  ◄── HARD GATE for production certification
        ↓
PHASE 14 — Observability (wall-clock/monotonic separation, overrun measurement)
        ↓
PHASE 15 — Frontend Integration (+ Frontend CI, closed in Phase 0)
        ↓
PHASE 16 — Backup / Disaster Recovery (real restore + post-restore reconciliation dry-run)
        ↓
PHASE 17 — Security Hardening / Penetration Testing
        ↓
PHASE 18 — Production Certification  ◄── HARD GATE
        ↓
OPSFORGE PAM V1 — v2.0.0-production
```

Phases 14 and 15 may run in parallel with each other and with the tail of Phase 13. PostgreSQL (Phase 5-Parallel) is never on this critical path — it is fast-follow, non-V1, architectural validation only.

---

## 21. Architecture Gates

**Gate 1 — Architecture Contract** (before Phase 3). Confirms the six-method `CredentialExecutor`, the KMS contract stub, and that the narrow credential-use operation (Item 4) is the only decrypt-shaped call defined.

**Gate 2 — SSH JIT Model** (before Phase 7). Confirms the sudoers.d mechanism, its write sequence, and the helper's allowlisted-operation boundary (Items 8.2, 11.1) against real Phase 3/4 executor behavior.

**Gate 3 — Session Broker** (before Phase 11). ADR accepted; preserves Item 14.1's full authorization chain and binding requirements; may propose implementation changes only with evidence and an ACR.

**Gate 4 — Production KMS** (before Phase 18). Fail-closed startup check proven; no production-like credential has touched the local provider since Phase 4.

**Gate 5 — Disaster Recovery** (before Phase 18). A real restore performed; post-restore reconciliation dry-run exercised at least once.

**Gate 6 — Security Certification** (before production release). Full matrix (Item 23) passes, including measured JIT-overrun evidence (Item 11.2); adversarial pass finds no unresolved critical finding.

---

## 22. Master Roadmap — the single canonical order

| Phase | Objective | Dependency | Tag |
|---|---|---|---|
| 0 | Stabilization | none | `v1.1.0-phase0-stabilized` |
| 1 | Architecture Contract + KMS contract stub (Gate 1) | 0 | `v1.2.0-architecture-contract` |
| 2 | Target Bootstrap + disposable SSH test environment + allowlisted helper | 1 | `v1.3.0-bootstrap-runbook` |
| 3 | SSH Executor (connect, host-key verify, corrected SSRF) | 2 | `v1.4.0-ssh-connection` |
| 4 | Real SSH Rotation (bootstrap key, first — Item 10.1) | 3 | `v1.5.0-real-rotation` |
| 5 | Rotation Engine / Scheduler | 4 | `v1.6.0-rotation-engine` |
| 5-Parallel | PostgreSQL Executor — NON-V1 | any time after 4 | n/a |
| 6 | Target Account Provisioning | 5 | `v1.7.0-account-provisioning` |
| 7 | JIT Privilege Elevation (Gate 2) | 6 | `v1.8.0-jit-provisioning` |
| 8 | JIT Revocation / Failure Recovery | 7 | `v1.9.0-jit-revocation` |
| 9 | Reconciliation | 8 | `v1.10.0-reconciliation` |
| 10 | Session Broker Architecture Decision (Gate 3, HARD) | 9 | ADR accepted |
| 11 | Brokered SSH Session | 10 | (tag set once Phase 10 resolves scope) |
| 12 | Credential Injection + Session Control | 11 | `v1.11.0-session-control` |
| 13 | Production KMS (Gate 4, HARD) | 12 | `v1.12.0-production-kms` |
| 14 | Observability | 13 | `v1.13.0-observability` |
| 15 | Frontend Integration | 13 | `v1.14.0-frontend-integration` |
| 16 | Backup / Disaster Recovery (Gate 5) | 14, 15 | `v1.15.0-backup-recovery` |
| 17 | Security Hardening / Penetration Testing | 16 | `v1.16.0-security-hardened` |
| 18 | Production Certification (Gate 6, HARD) | 17 | `v2.0.0-production` |

This table is the single source of truth for phase numbers and names. Every other reference to a phase number anywhere in this document was checked against it while this version was written.

---

## 23. Security Test Matrix

| Threat class | First applicable phase | Test approach |
|---|---|---|
| Bootstrap privilege escalation via `opsforge-svc` | 2 | Attempt to use `opsforge-svc`'s sudo rights for anything other than invoking the helper; attempt to pass the helper an out-of-namespace file path or an unmanaged account — both must be rejected by construction |
| SSRF / arbitrary target access | 3 | Rejection test on resolve-once-then-connect-to-validated-address; `internal=true` does not bypass validation |
| Host-key spoofing | 3 | Live mismatch-rejection test against the disposable target |
| Credential leakage into logs | 3, extended every phase after | Automated log-scraping test on every new plaintext-touching path |
| Command/shell injection into the helper | 3–7 | Malformed/malicious positional-argument test against every helper operation |
| Rotation add-then-verify-then-remove ordering | 4 | Test that killing the process between steps never leaves zero valid keys |
| Bootstrap vs. human rotation severity distinction | 4, 6 | Confirm a bootstrap rotation failure and a human-account rotation failure are classified and alerted at different severities |
| Worker duplication/crash | 5 | Concurrency + crash-injection tests; idempotency proven under retry |
| Two users mapped to one OS account | 6 | Explicit uniqueness-violation rejection test |
| `provision_account`/`remove_account` interrupted mid-sequence | 6 | Deliberately kill the helper between steps; confirm compensating rollback runs and, if the resulting state can't be confirmed, the operation reports security uncertainty rather than a false success |
| User-departure `REMOVED` automation | 6, 15 | Simulate org-removal event; verify automatic, verified, audited target account disable — never left orphaned |
| Sudoers write-path integrity (via helper) | 7 | Symlink-attack test, invalid-syntax rejection via `visudo -c`, partial-write cleanup test |
| Wildcard/wide-scope grant rejection | 7 | Policy-schema rejection test for any `ALL`/wildcard command entry absent an explicit reviewed exception |
| JIT expiry overrun measurement | 7–8 | Live test measuring `observed_overrun` against the declared Δ ≤ 5s bound |
| Worker-down JIT expiry scenario | 8 | Kill the worker with an active grant approaching expiry; confirm reconciliation (Layer 3) completes revocation on worker restart, and confirm the residual-risk window is measured, not hidden |
| Revocation failure | 8 | Live failure test → `REVOCATION_FAILED`, alertable |
| Unknown-origin sudoers file (reconciliation) | 9 | Deliberately plant an unrecognized `opsforge-jit-*` file; must never be auto-deleted |
| Broker credential-use authorization bypass | 11 | Attempt a credential-use request missing or mismatching any of the required bound IDs (Item 14.1); must be denied |
| Session hijacking / termination bypass | 10–12 | Finalized alongside Phase 10's ADR |
| Broker-compromise / crash scenario | 12 | Simulate broker failure; Layer 2 (Item 14.2) must still remove privilege within the bounded window, worker permitting |
| KMS failure | 13 | Fail-closed test — no insecure fallback |
| Scheduling-latency safety margin | 14 | Deliberately delayed scheduler test proving the margin holds |
| Cross-object authorization on new models | Every phase introducing a new object type | Reuses the proven `tests/ownership/` pattern |

---

## 24. Observability & Time Model

- **Authorization decisions** (grant `issued_at`/`expires_at`, audit timestamps) are stored and compared in **UTC wall-clock time**.
- **Scheduling-loop internals** (Item 11.2's expiry-enforcement scheduler) use a **monotonic clock** to compute "time until next check," so a wall-clock jump can't cause the loop to double-fire or skip a check.
- **The expiry decision itself is always a wall-clock UTC comparison** at the moment of check.
- **Target-reported time is never authoritative** for any security decision.
- The scheduling-latency safety margin (formerly, incorrectly, "negative-skew buffer") is sized to the expiry-enforcement scheduler's own interval (Item 11.2) — it addresses scheduler delay, not clock skew between systems, and is named accordingly throughout this document.
- **`expiry_time`, `revocation_start`, `revocation_complete`, and `observed_overrun` are recorded for every JIT grant** (Item 11.2) and surfaced in observability dashboards from Phase 7 onward.

Health/readiness for API + worker + broker processes, correlation IDs end-to-end, and alerts on every failure state are unchanged.

---

## 25. Backup / Disaster Recovery

Database + configuration + KMS/key recovery, plus the mandatory post-restore reconciliation dry-run procedure (detect mismatches using Item 12's safe-retry-vs-manual classification, resolve manually where required, only then re-enable automated rotation/JIT) before automation resumes against a restored environment.

---

## 26. Production Deployment

**Development:** `LocalEnvironmentKeyProvider` allowed.

**From Phase 4 onward:** no production-like privileged credential may be used with the local/dev KMS provider — either a staging KMS instance is used, or the credential is explicitly classified disposable/development and never promoted.

**Pre-production:** the production-like KMS contract (Phase 1) is tested against a staging/real KMS instance no later than Phase 4.

**Production:** real KMS mandatory; startup fails closed if the active provider is the local one under `APP_ENV=production`.

Single-node deployment topology; HA/multi-region deferred.

---

## 27. Production Certification Gates

`v2.0.0-production` requires, with real-target evidence:

1. Real target — at least one live SSH target.
2. Real rotation — keypair actually changes on the target, add-then-verify-then-remove sequence demonstrated for both bootstrap (Item 10.1) and a human account (Item 10.2).
3. Real verification — the new key confirmed to work before the old one is removed.
4. Real target account provisioning — a per-human OS account created, verified, isolated from other users' accounts.
5. Real JIT — privilege actually provisioned via the helper-mediated sudoers.d mechanism.
6. **Real, measured expiry enforcement** — `observed_overrun` demonstrated within the declared Δ ≤ 5s bound under normal operating conditions, with a documented test of the worker-down scenario showing reconciliation's eventual recovery (Item 11.2).
7. Real revocation — privilege actually removed, verified, two-layer termination demonstrated including a simulated broker failure.
8. Real session — a user connects through the broker to a real target, with Item 14.1's full credential-use authorization chain demonstrated, including at least one deliberately-malformed request that Vault correctly denies.
9. Credential protection — the raw target-account credential never reaches the browser.
10. Reconciliation — demonstrably distinguishes a safe-retry case from a manual-intervention case in testing.
11. Real automated account removal — a simulated user-departure event results in a verified, audited target-account disable, with no orphaned account left behind.
12. Audit — complete, attributable trail across all four planes.
13. KMS — production key management active; dev provider provably cannot boot in production; no production-like credential touched the dev provider from Phase 4 onward.
14. Recovery — a real restore performed, including the post-restore reconciliation dry-run.
15. Security — the full Item 23 matrix passes; adversarial pass finds no unresolved critical finding, including an explicit attempt to escalate `opsforge-svc` beyond its helper boundary.
16. Operations — monitoring/health/alerting live, shown to fire on injected failures including a simulated broker-compromise and a simulated worker-down scenario.

Only when all sixteen pass: tag `v2.0.0-production`.

---

## 28. Risk Register

| Risk | Priority | Mitigation |
|---|---|---|
| Bootstrap ordering bug reaches implementation | P0 | Corrected — bootstrap is Phase 2, before anything requiring target authentication; every phase reference checked against Item 22's table |
| Human↔target identity mapping left undesigned | P0 | Item 9 — full design, its own phase, its own lifecycle |
| Broker credential retrieval unauthorized/underspecified | P0 | Item 14.1 — full binding chain, verified by Vault, fail-closed |
| JIT privilege outlives its grant with no honest bound | P0 | Item 11.2 — declared Δ ≤ 5s, three explicit layers, measured evidence, residual risk stated plainly |
| `opsforge-svc` becomes a de facto remote-root mechanism | P0 | Item 8.2 — restricted to invoking one fixed, allowlisted, root-owned helper; no direct sudoers/authorized_keys write access |
| Rotation mechanism ambiguity | P0 (resolved) | Item 10 — keypairs only, exact ordering, split into bootstrap/human lifecycles |
| Orphaned target accounts after user departure | P1 | Item 15 — `REMOVED` is automatic, verified, audited; reconciliation sweeps for orphans as backstop |
| Two grants' narrow privileges combine into an unintended broad one | P1 | Item 11.3 — wildcard grants forbidden by default at the policy layer |
| Reconciliation alerts forever with no path to resolution | P1 | Item 12 — safe-retry vs. manual-intervention classification |
| Simultaneously-dead worker defeats both termination layers | P1 (residual, disclosed) | Item 11.2/14.2 — explicitly documented limitation; reconciliation recovers once the worker restarts; revisitable via ACR with real overrun evidence |
| PostgreSQL work expands and delays the core SSH path | P1 | Explicitly non-blocking, parallel |
| Worker/executor process becomes a high-value compromise target | P1 | Least-privilege review at Phase 5 exit; adversarial review at Phase 17, including the helper boundary specifically |
| `LocalEnvironmentKeyProvider` reaches a production-like credential before the KMS gate | P1 | Barred from Phase 4 onward |
| Frontend work drifts ahead of backend capability | P2 | Priority order unchanged |
| Scope creep under schedule pressure | P1 | Forbidden-scope lists plus the PAM Direction Gate at every phase exit |

---

## 29. Architectural Decision Records

1. V1 is single-tenant.
2. Existing foundation is extended, never rewritten, absent a concrete defect.
3. PostgreSQL is non-blocking, parallel validation, not a V1 requirement.
4. `CredentialExecutor` remains six methods.
5. `Resource` remains the permanent target abstraction, extended in place.
6. Bootstrap precedes rotation and JIT in the roadmap — Phase 2, before Phases 3/4/7 — a real, evidence-based dependency correction.
7. Human↔target identity is a designed, first-class model (Item 9), not an assumed detail.
8. V1 JIT mechanism is a per-grant `/etc/sudoers.d/` drop-in file, written exclusively through the bootstrap helper (Item 8.2), never by `opsforge-svc` directly.
9. JIT is named and scoped correctly as privilege elevation for an existing identity, not identity creation (Item 11).
10. Session termination is two independent layers with an explicitly disclosed worker-availability dependency, not one unconditional guarantee (Item 14.2).
11. The session-broker ADR may challenge the identity-chain and credential-authorization implementation with evidence, via ACR — not silently pre-decided (Item 14.1).
12. Production KMS is a certification-blocking gate with a fail-closed startup check; bars production-like credentials from the dev provider starting at Phase 4.
13. Rotation, JIT, and revocation share one failure-state vocabulary with an operation-failure-vs-security-uncertainty severity split.
14. Reconciliation V1 scope is limited to JIT-grant and rotation state, with safe-retry vs. manual-intervention classification.
15. Break-glass/emergency access is deferred from V1 entirely; no informal break-glass path exists anywhere in this design, including the helper.
16. A target-side privileged expiry-enforcement agent was considered and rejected; the resulting worker-availability dependency is disclosed, not hidden (Item 11.2).
17. Wildcard sudoers grants are forbidden by default; privilege-conflict risk is resolved at the policy layer (Item 11.3).
18. Vault Plane is a shared library, not a network service; there is exactly one credential-release code path in the system (the credential-use operation, Items 4 and 14.1), never a generic decrypt-by-ID call.
19. **`opsforge-svc` is restricted to invoking one fixed, root-owned, fixed-path helper executable exposing only allowlisted, sequenced-and-verified operations (`provision_account`, `remove_account`, `add_jit_grant`, `remove_jit_grant`), each with a defined compensating-rollback and security-uncertainty fallback rather than a claim of database-style atomicity — it never holds direct sudo rights to write sudoers or `authorized_keys` files, or the ownership manifest, itself (Item 8.2).**
20. **Bootstrap credentials and human target-account credentials are two distinct lifecycles (Items 10.1, 10.2) sharing one rotation mechanism, with different failure severities.**
21. **Target-account `REMOVED` is an automatically triggered, verified, audited event on organizational departure, not a manual best-effort action (Item 15).**
22. Any change to this plan's scope, sequencing, or architecture requires an Architectural Change Request.
23. Day-by-day tasks are generated at each phase's entry, not pre-written for the whole roadmap.

---

## 30. Anti-Drift Rules

Before adding anything not already in this document, answer all ten questions; if any answer is unfavorable, do not build it:

1. Is this feature part of PAM? 2. Does it control privileged access? 3. Does it reduce credential exposure? 4. Does it improve target-side enforcement? 5. Does it improve accountability? 6. Is it required for V1? 7. What existing phase does it belong to? 8. What dependency does it introduce? 9. What security boundary does it affect? 10. Does it require an ACR?

---

## 31. Final Canonical Execution Order

```
PHASE 0  → Stabilization
PHASE 1  → Architecture Contract
PHASE 2  → Target Bootstrap + Reproducible SSH Test Target (+ allowlisted helper)
PHASE 3  → SSH Executor
PHASE 4  → Real SSH Credential Rotation (bootstrap key first)
PHASE 5  → Automated Rotation Engine
PHASE 6  → Human Target Account Provisioning
PHASE 7  → JIT Privilege Provisioning
PHASE 8  → JIT Privilege Revocation
PHASE 9  → Target Reconciliation + Recovery
PHASE 10 → Session Broker Architecture Decision
PHASE 11 → Brokered SSH Session
PHASE 12 → Session Enforcement + Credential Injection
PHASE 13 → Production KMS
PHASE 14 → Observability
PHASE 15 → Operational Frontend Integration
PHASE 16 → Backup + Disaster Recovery
PHASE 17 → Security Hardening / Adversarial Testing
PHASE 18 → Production Certification
        ↓
OPSFORGE PAM V1
```

PostgreSQL and additional protocols are Fast-Follow and do not block V1.

Versioning convention: phase tags (`v1.x.x-phaseN-name`) are internal milestones, never production releases. A production-candidate build before certification completes is tagged `v2.0.0-rcN`. Only after all Item 27 gates pass is `v2.0.0-production` tagged.

---

## 32. Canonical Project Direction

OpsForge is building a security-first Privileged Access Management platform. It extends a verified, working identity/RBAC/policy/vault foundation with an Execution Plane that safely reaches real external targets and a Session Plane that brokers privileged access without exposing raw credentials. Database state is never treated as proof that something happened on a real system. Version 1 targets exactly one protocol, SSH, end-to-end: a scoped bootstrap identity, restricted to one allowlisted target-side helper, established before anything else; real SSH-keypair rotation as two distinct lifecycles; per-human target-account provisioning with a fully automated, verified removal path; real just-in-time privilege elevation with a declared, measured expiry-overrun bound and an honestly disclosed residual risk; reconciliation that distinguishes safe automatic recovery from genuinely uncertain state; and a brokered session whose every credential release is bound to a full, verified authorization chain and protected by two independent termination layers — all audited and recoverable. PostgreSQL support exists only to validate that the architecture generalizes and never blocks or delays the SSH path. Multi-tenancy, session recording, break-glass access, additional protocols, and cosmetic frontend work are explicitly deferred. Scope only grows through a documented Architectural Change Request.

---

## 33. First Implementation Milestone

**Phase 0, Day 1: correct the product-identity strings in `README.md` and `pyproject.toml`, then proceed through Phase 0's remaining stabilization tasks, then Phase 1's minimal architecture contract.** The first line of genuinely new capability code is Phase 2's target bootstrap, including the allowlisted helper.

Two distinct milestones follow, and this document does not conflate them:

- **First real external interaction** — Phase 3: OpsForge establishes and verifies an SSH connection against a reproducible disposable target, using the bootstrap identity Phase 2 established. Nothing on the target changes state yet.
- **First real, state-changing PAM capability** — Phase 4: OpsForge changes a real target credential (the bootstrap account's own key), verifies the new credential works, and only then updates Vault state. This is the point OpsForge earns the label "PAM" — a real target changed, not merely a database row.

---

## 34. Definition of Done for V1

- [ ] Real SSH target registered, validated, host-key pinned, corrected SSRF model enforced
- [ ] Target bootstrap identity established before any rotation/JIT code runs; `opsforge-svc` restricted to invoking the single allowlisted helper, never holding direct sudoers/`authorized_keys` write rights itself
- [ ] Real SSH keypair rotation, add-then-verify-then-remove, demonstrated live for both the bootstrap lifecycle and the human-account lifecycle, distinctly classified
- [ ] Per-human target-account provisioning demonstrated live: unique OS account per (user, target), verified, isolated
- [ ] JIT grant provisions real target-side sudo privilege via the helper-mediated, `visudo`-validated sudoers.d sequence — demonstrated live
- [ ] JIT expiry enforcement demonstrated live with `observed_overrun` measured within the declared Δ ≤ 5s bound; a worker-down scenario tested and its recovery via reconciliation demonstrated
- [ ] Two-layer session termination demonstrated live, including a simulated broker-failure scenario
- [ ] Broker credential-use authorization demonstrated live, including a deliberately malformed/unbound request correctly denied by Vault
- [ ] Reconciliation demonstrably distinguishes a safe-retry case from a manual-intervention-required case in testing
- [ ] Session broker chosen via accepted ADR; any proposed change to the identity/authorization chain documented via ACR with evidence
- [ ] Raw target-account credential never reaches the browser
- [ ] Automated, verified, audited target-account removal demonstrated on a simulated user-departure event
- [ ] Every failure state reachable, alertable, documented, correctly classified by severity
- [ ] Production KMS active; dev provider provably cannot boot under `APP_ENV=production`; no production-like credential touched the dev provider from Phase 4 onward
- [ ] Full audit trail across all four planes, attributable, complete
- [ ] Observability: wall-clock/monotonic time separation implemented, scheduling-latency margin proven, JIT-overrun metrics live
- [ ] Backup/recovery: a real restore performed, post-restore reconciliation dry-run exercised at least once
- [ ] Full security test matrix passes, including the helper-escalation and worker-down scenarios; adversarial pass finds no unresolved critical issue
- [ ] Reproducible disposable test-target environment supports fault injection for every listed failure class
- [ ] Frontend covers targets/accounts/JIT/sessions/rotation/audit workflows; frontend CI gates every merge
- [ ] All sixteen Item 27 gates pass
- [ ] Tagged `v2.0.0-production`

# OPSFORGE — MASTER IMPLEMENTATION DIRECTIVE

This document sits **above** `OPSFORGE — CANONICAL MASTER PRODUCTION PLAN — FINAL FROZEN VERSION` and governs *how* an implementation agent (e.g. Antigravity) works against it. It does not restate the plan's architecture — it tells the agent how to turn that frozen architecture into code without inventing its own.

**Repository:** `lokilokith/Devops`
**Base commit:** `e58671f`
**Tag:** `v1.0.0-phase1-final`
**Governing document:** `OPSFORGE — CANONICAL MASTER PRODUCTION PLAN — FINAL FROZEN VERSION` (attached separately)

---

## Primary objective

Implement OpsForge PAM V1 completely and production-certifiably according to the attached Master Production Plan.

The Master Production Plan is **frozen**. Do not redesign, reinterpret, simplify, weaken, reorder, or silently expand its architecture, security model, scope, invariants, phase dependencies, or production gates.

The final result must satisfy the complete Definition of Done (Master Plan Item 34) and all sixteen Production Certification requirements (Master Plan Item 27).

---

## Execution mode

Work phase by phase, beginning with Phase 0, in the exact order the Master Plan's Item 22 table defines. Do not attempt to implement the entire roadmap in one undifferentiated pass.

For each phase:

1. Inspect the current repository and existing implementation — not this directive's assumptions about it.
2. Map the Master Plan's requirements for that phase to the actual repository structure.
3. Produce a concrete implementation checklist for that phase: exact files, modules, models, services, endpoints, migrations, jobs, and tests required — derived from the repository as it actually is, not invented in advance.
4. Implement the phase completely.
5. Add or update automated tests, including the failure/security tests the Master Plan's Item 23 matrix requires for that phase.
6. Run the complete relevant test/security/static-analysis suite.
7. Verify every phase acceptance criterion against actual evidence — a passing test suite alone is not evidence of target-side behavior.
8. Fix failures before proceeding; never carry a known failure into the next phase.
9. Perform a security review of the completed phase against the Master Plan's invariants (Item 16) for that phase.
10. Update implementation documentation where it supports building, verifying, or operating the system — not documentation for its own sake.
11. Create the phase's Git checkpoint/tag exactly as specified in the Master Plan's Item 22 table.
12. Only then proceed to the next phase.

A phase is not complete because code compiles or unit tests pass against a database. It is complete when its target-side behavior, security invariants, failure handling, verification, and auditability are demonstrated — per the Master Plan's own phase-contract template (Item 20).

---

## Repository-first rule

Before writing implementation code for a phase, inspect the repository thoroughly. Determine: existing application structure, framework and runtime, database layer, existing models, migrations, authentication, RBAC, policy engine, Vault implementation, KMS abstraction, existing audit system, worker/background-job system, container configuration, CI/CD, existing test architecture (in particular the `tests/ownership/` pattern the Master Plan requires reusing), configuration/environment handling, existing frontend, and existing security tooling.

Do not rewrite working foundation code without concrete evidence of a defect. Extend the existing foundation wherever the Master Plan requires extension (its default posture throughout).

---

## Architecture lock

The following are constraints carried directly from the Master Plan, restated here because they are the ones most likely to be quietly reinterpreted under implementation pressure — not a substitute for reading the plan itself:

- Four planes: Control, Vault, Execution, Session.
- V1 is single-tenant. SSH is the V1 target protocol.
- `Resource` remains the permanent target abstraction — no separate `Target` model.
- Web/API and worker remain separate OS processes; the worker is the only process with outbound access to privileged targets.
- Vault Plane is a shared library, not a network service; there is no generic `decrypt(credential_id)` operation anywhere.
- Every credential release uses the complete authorization binding in Master Plan Item 14.1 (session, grant, user, resource, target-account-binding, credential IDs, plus expiry) — an unbound or partially-bound request is always denied.
- Plaintext credentials never cross the web/API ↔ worker process boundary, under any circumstance.
- `opsforge-svc` never receives direct filesystem-write sudo privileges; it may invoke only the fixed root-owned helper executable (Master Plan Item 8.2).
- The helper exposes only its explicitly allowlisted operations (`provision_account`, `remove_account`, `add_jit_grant`, `remove_jit_grant`) — each a sequenced, verified operation with a defined compensating-rollback and security-uncertainty fallback, **never implemented or described as a database-style atomic transaction**, since the underlying OS operations cannot be made atomic in that sense.
- JIT uses helper-mediated `sudoers.d` grants, validated with `visudo` **before** the file is made live (temp file → validate → only then atomic rename) — never the reverse order.
- Wildcard privilege grants are forbidden by default.
- JIT expiry enforcement retains its explicitly documented worker-availability limitation (Master Plan Item 11.2) — do not implement or claim a guarantee stronger than the plan's own SLO framing.
- Database state is never accepted as proof of target-side success.
- Every target-mutating operation is idempotent by construction.
- Production cannot use the local/dev KMS provider (barred from Phase 4 onward, not just at the KMS gate).
- No production release until all sixteen Item 27 certification gates pass, with real-target evidence for each.
- Any scope addition, or any change to the above, requires an Architectural Change Request — implemented as a documented decision record, not a silent code change.

---

## No silent architectural decisions

If implementation requires a decision the Master Plan does not explicitly make:

1. Check whether the existing repository already establishes the answer — if so, preserve that existing convention.
2. If it doesn't, choose the smallest implementation consistent with the frozen architecture.
3. Document the decision (where it lives, why it was made) alongside the code it affects.
4. If the decision would change architecture, a security boundary, phase order, scope, or a non-negotiable invariant, **stop and raise an Architectural Change Request instead of implementing it silently.**

"Reasonable assumption" is never sufficient justification for a change that Step 4 covers — that's precisely the class of decision the ACR process exists to catch.

---

## Security-first implementation

For every security-sensitive capability, implement: positive-path tests, negative-path tests, authorization tests, object-level ownership tests (reusing the existing `tests/ownership/` pattern), malformed-input tests, concurrency tests where relevant, retry/idempotency tests, failure-injection tests, target-side verification tests, audit verification, and log/secret-leakage tests.

A passing database-only test is insufficient wherever the Master Plan requires target-side behavior (rotation, JIT provisioning/revocation, account provisioning/removal, session establishment) — the Master Plan's own invariant that database state is never proof of target-side success applies to the test suite exactly as much as it applies to production behavior.

---

## Phase gate

Never mark a phase complete merely because implementation exists. Before advancing, produce evidence for:

```
Requirement → Implementation → Test → Observed result → Security verification
```

Every phase has an explicit pass/fail gate (the Master Plan's Architecture Gates, Item 21, for the phases that carry one; its per-phase acceptance criteria, Item 20, for all of them). If a requirement can't yet be demonstrated because a later phase provides its dependency, document that dependency explicitly rather than marking the requirement complete.

---

## Failure policy

Never hide a failure. If a test fails: diagnose the actual cause, fix it, rerun the test, rerun the relevant regression suite, and verify no security invariant was weakened by the fix.

If target state cannot be confidently determined at any point, classify the condition as security uncertainty per the Master Plan's failure model (Item 13) — never convert an uncertain target state into a reported success. This applies with particular force to `provision_account`/`remove_account` (Master Plan Item 8.2): an interrupted sequence that cannot be confirmed fully rolled back and re-verified is a security-uncertainty finding, not a retried "success."

---

## Speed, correctly framed

The objective is: **complete the entire roadmap as fast as possible, but never advance a phase without passing its verification gate.** This is deliberately not the same as "produce the complete final output as soon as possible" — that framing rewards volume over verified correctness, which is the wrong incentive for a PAM system specifically. A large volume of quickly-produced code that hasn't cleared its phase gates is not progress against this directive; it's technical debt with a security label on it.

Optimize implementation speed without sacrificing correctness. Use parallel work only where the Master Plan explicitly permits it (e.g., Phases 14/15 against the tail of Phase 13; the PostgreSQL parallel track). Do not spend time on: cosmetic frontend work ahead of operational capability, speculative abstractions, deferred protocols or features, unnecessary rewrites, or documentation that doesn't support implementation, verification, or operation.

Prefer: small, cohesive changes; reuse of the verified foundation; automated testing; reusable fixtures; the deterministic disposable target environment (Master Plan Item 22); idempotent operations; scripted verification; phase-level automation.

---

## Final objective and final report

Continue through all phases until: all implementation phases are complete; all required tests pass; all security tests pass; all target-side behaviors are demonstrated; all reconciliation scenarios pass; production KMS is active; disaster recovery is demonstrated; the full security matrix passes; adversarial testing passes; all sixteen Production Certification gates pass; and the Master Plan's Item 34 Definition of Done is satisfied.

Only then tag `v2.0.0-production`.

The final response to the person operating this project must include:

1. Completed phase list, with tags.
2. Git commits/tags for each.
3. Implementation summary.
4. Architecture summary (confirming no drift from the frozen plan, or documenting the ACRs if any were needed).
5. Security controls implemented.
6. Test results.
7. Target-side verification evidence.
8. Production certification evidence, item by item against Master Plan Item 27.
9. Known residual risks (in particular, the Item 11.2 worker-availability dependency and any other explicitly disclosed limitation — these must be restated here, not omitted because the project shipped).
10. Exact commands required to deploy and operate the final system.

Do not declare OpsForge production-ready until every mandatory gate has actual, demonstrated evidence behind it — not until the code exists, and not until the tests are green in isolation from target-side proof.

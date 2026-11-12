# OpsForge AuditLog Domain Specification

**Status:** Pending Review

**Scope:** AuditLog domain only

**Applies to:** Future implementation in `app/audit/` and all historical records generated across the platform

**Out of scope:** SQLAlchemy models, Python code, migrations, repositories, APIs, SIEM configuration, application tracing, and system debug logging

---

## 1. Executive Summary

The AuditLog domain is the immutable forensic ledger of the OpsForge Privileged Access Management (PAM) platform. It provides the permanent, append-only history of every security-relevant event, decision, and action taken within the system.

Following the Architecture-First methodology, this domain is explicitly decoupled from standard application logging (e.g., debug, trace, exceptions). It exists solely to fulfill compliance mandates, enable digital forensics, and support incident response. The AuditLog ensures that OpsForge acts as a trusted, tamper-evident authority for all privileged access operations.

---

## 2. Business Purpose

In a PAM platform, operational security is meaningless without non-repudiation. Organizations must definitively answer: *Who did what, to which target, at what time, from where, and who approved it?*

The AuditLog domain fulfills this requirement by isolating business security events into a specialized, highly structured schema. It provides the legally defensible evidence required for security auditing, compliance (SOC 2, ISO 27001, PCI-DSS), and post-incident investigations, independently from ephemeral application logs.

---

## 3. Responsibilities

- Providing an append-only, immutable record of security-relevant events.
- Capturing the complete context of an action (Actor, Target, Time, Source IP, Metadata).
- Tying together distributed events using a `correlation_id` to trace complex workflows (e.g., Request → Approval → Session).
- Storing structured metadata for flexible forensic queries without schema changes.
- Guaranteeing time-synchronization consistency by enforcing strict UTC timestamps.
- Serving as the authoritative source for external SIEM (Security Information and Event Management) integrations.

---

## 4. Out-of-Scope Responsibilities

- **Application Logging:** AuditLog does not record HTTP 500 exceptions, stack traces, or debug statements. Those belong to the Logging subsystem.
- **Business Logic Evaluation:** AuditLog does not make decisions or enforce policy; it only records historical facts.
- **Workflow Control:** AuditLog does not transition AccessRequests or Approvals.
- **Session Brokering:** It does not manage proxy connections, though it records their initiation and termination.
- **Data Archival Execution:** The domain defines the *Archived* state, but external infrastructure policies execute the physical data movement to cold storage.

---

## 5. DDD Boundary Statement

AuditLog is a core domain entity in the `audit` bounded context. It strictly owns the forensic event payload, severity, categorizations, identity references, and timestamp immutability. It does not own the lifecycles of the entities it references (Users, Resources, Requests) and must remain entirely passive, accepting records from other domains without participating in their transactional logic.

---

## 6. Audit Event Lifecycle

Audit events have a fundamentally different lifecycle than transactional data; they never move backward and are never modified.

### 6.1 Lifecycle States
- **Created:** The event is actively being written to the database in real-time.
- **Stored:** The event is finalized in the operational database and available for immediate reporting and forensic queries. (Terminal in the operational database)
- **Archived:** The event has aged past the operational retention period and is moved to long-term cold storage or an external compliance vault. (Terminal in cold storage)

### 6.2 Immutability Constraints
- **Append-Only:** AuditLog records are inserted once.
- **Never Updated:** An `UPDATE` operation is strictly prohibited by business rule and database constraint.
- **Never Deleted:** A `DELETE` operation is strictly prohibited in the operational database; data only exits via strict, compliant archival mechanisms.

---

## 7. Relationships

Because the AuditLog is a ledger, its relationships are strictly unidirectional references *from* the log *to* the entities.

- **User (Actor/Target):** References the human initiating the action (`actor_user_id`) or the subject of an identity change.
- **Role:** References privilege assignments and policy definitions.
- **Resource:** References the operational target (`resource_id`).
- **AccessRequest:** References the intent workflow (`access_request_id`).
- **Approval:** References authorization decisions (`approval_id`).
- **Future Session Domain:** Will reference the physical proxy connection.
- **Future Policy Engine:** Will reference automated decisions and risk scores.
- **Future Authentication:** Will reference login attempts, MFA challenges, and token issuance.

*Crucially, if a referenced User or Resource is retired or deleted, the AuditLog foreign keys must remain intact (often enforced by soft-deletes in other domains) or rely on the embedded metadata to preserve historical context.*

---

## 8. Attribute Definitions

| Attribute | Purpose | Type | Required | Mutable | Default | Validation Rules |
|---|---|---|:---:|:---:|---|---|
| id | Primary business key | UUID v4 | Yes | No | Generated | Immutable |
| event_type | Specific action (e.g., `user.login.failed`) | String | Yes | No | None | Standardized taxonomy |
| event_category | High-level grouping | Enum | Yes | No | None | Must be an approved category |
| severity | Risk level | Enum | Yes | No | None | Must be an approved severity |
| actor_user_id | Identity of the initiator | UUID v4 | No | No | Null | Nullable for System/Machine actors |
| actor_type | Classification of the actor | Enum | Yes | No | `user` | E.g., `user`, `system`, `policy_engine` |
| target_entity_type | The domain of the affected object | String | Yes | No | None | E.g., `resource`, `user`, `access_request` |
| target_entity_id | The ID of the affected object | UUID v4 | No | No | Null | Nullable for global events |
| resource_id | Optional explicit target link | UUID v4 | No | No | Null | Direct link for resource access |
| access_request_id | Optional explicit workflow link | UUID v4 | No | No | Null | Direct link for JIT workflows |
| approval_id | Optional explicit decision link | UUID v4 | No | No | Null | Direct link for authorization |
| ip_address | Network origin | IPAddress | No | No | Null | Must be valid IPv4/IPv6 format |
| user_agent | Client identification | String | No | No | Null | Truncated to safe length |
| correlation_id | Cross-event tracing | UUID v4 | Yes | No | Generated | Links distributed events together |
| metadata | Arbitrary event context | JSONB | No | No | Null | Redacted schema-less payload |
| event_timestamp | When the action occurred | Timestamp | Yes | No | None | Immutable UTC |
| created_at | When the log was persisted | Timestamp | Yes | No | Auto | Immutable UTC |

---

## 9. Event Categories

To support efficient SIEM filtering, events are categorized at a high level:

- **Authentication:** Logins, logouts, MFA challenges, password resets.
- **Authorization:** Role assignments, policy evaluations.
- **Access Request:** Submission, cancellation, expiration of JIT intent.
- **Approval:** Decisions, delegations, escalations, break-glass executions.
- **Resource:** Target creation, modification, retirement.
- **Administrative:** System configuration, tenant changes.
- **Security:** Account lockouts, anomalous activity, privilege escalation.
- **Policy:** Engine evaluations, rule modifications.
- **System:** Platform startup, backup execution, key rotation.
- **Emergency:** Any action taken under break-glass conditions.

---

## 10. Severity Levels

Severity drives alert routing in external monitoring systems:

- **Information:** Routine operational events (e.g., user logged in, resource created).
- **Low:** Minor anomalies or administrative actions (e.g., user updated their name).
- **Medium:** Security-relevant boundary events (e.g., access request submitted, failed login).
- **High:** Critical security transitions (e.g., break-glass approval, user suspended, multiple MFA failures).
- **Critical:** System-threatening events (e.g., root configuration changed, suspected breach, policy engine bypassed).

---

## 11. Business Rules

### 11.1 Absolute Immutability
Records are append-only. No application role, regardless of privilege, is permitted to modify or delete an AuditLog record.

### 11.2 Security Event Mandate
Every action that changes the state of a core domain (User, Role, Resource, AccessRequest, Approval) MUST generate at least one corresponding AuditLog event.

### 11.3 Correlation Integrity
Events occurring within the same logical transaction or workflow (e.g., a multi-stage approval chain for a single request) must share a common `correlation_id` to allow forensic reconstruction.

### 11.4 Time Synchronization
All timestamps must be recorded in absolute UTC to ensure global correlation across distributed systems.

---

## 12. Validation Strategy

### 12.1 Database Validation
- `id` is primary key.
- No `ON DELETE CASCADE` from parent tables (Audit records must survive parent deletion).
- Strict `NOT NULL` constraints on required context fields.
- Insert-only permissions enforced at the database user level for the application connection.

### 12.2 Application Validation
- Standardized taxonomy enforcement for `event_type`.
- IPv4/IPv6 format validation for `ip_address`.
- Payload sanitization before writing to the `metadata` JSONB column.

### 12.3 Business Validation
- Ensure `actor_user_id` is captured if `actor_type` is `user`.
- Enforce that `event_timestamp` cannot be artificially backdated or set in the future.

### 12.4 Security Validation
- Redaction of all secrets, passwords, tokens, and PII from the `metadata` payload before persistence.

---

## 13. Security Considerations

- **Integrity & Tamper Resistance:** The database should eventually support cryptographic hashing or blockchain-style chaining of logs to guarantee tamper evidence against highly privileged insider threats.
- **Non-Repudiation:** The strict capture of `actor_user_id`, `ip_address`, and `user_agent` prevents users from denying their actions.
- **Evidence Preservation:** The table must be designed so that it can be exported directly for legal chain-of-custody requirements.
- **Compliance:** Satisfies strict auditing controls required by zero-trust architectures and regulatory frameworks.

---

## 14. Audit Expectations (Meta-Audit)

### 14.1 What Must Always Be Audited
- All authentication events (success, failure, MFA, token refresh).
- All authorization decisions (approvals, rejections).
- All changes to Identity (User/Role modifications, lifecycle state changes).
- All target interactions (Resource creation, session initiation).
- All administrative platform configurations.

### 14.2 What Should Never Be Audited
- Passwords, cryptographic keys, and MFA seeds.
- Session tokens, API keys, or OAuth payloads.
- Highly sensitive PII not required for forensic tracing.
- High-volume read operations (e.g., viewing a dashboard), unless explicitly flagged by a strict policy, as this overwhelms the ledger.

---

## 15. Future Compatibility

This domain is designed as a universal sink, highly optimized for integration without requiring redesign:
- **SIEM / Log Aggregation:** The flat, categorical schema is easily consumed by Splunk, Elastic, Microsoft Sentinel, QRadar, and Chronicle.
- **Streaming Export:** The append-only nature allows seamless tailing via Syslog, Kafka, or AWS Kinesis/EventBridge without complex change-data-capture logic.
- **External Compliance Systems:** The standardized JSONB `metadata` column absorbs future schema requirements from specific regulatory reporting tools instantly.

---

## 16. Architecture Self-Review

### 16.1 Constraint Checks
- **No Application Logs:** Domain explicitly rejects debug/trace logs. (Pass)
- **Immutable Ledger:** Append-only, never deleted, UTC only. (Pass)
- **Decoupled Workflows:** AuditLog controls no business logic and acts solely as an observer. (Pass)
- **No Implementation:** Document strictly focuses on DDD boundaries and constraints without ORM syntax. (Pass)

### 16.2 Simplification Review
By combining a strict relational structure for core forensic pillars (Who, When, Where, Type, Target) with a flexible JSONB `metadata` payload (for the "What else"), the schema strikes the perfect balance between fast indexing for SIEMs and future-proof extensibility.

### 16.3 Final Assessment
The AuditLog domain provides a mathematically robust, tamper-resistant foundation for OpsForge. It fulfills every requirement for an enterprise PAM system's compliance and forensic capabilities while remaining entirely decoupled from the operational transactional workflows.

**Recommendation:** PENDING ARCHITECTURE REVIEW -> READY FOR APPROVAL

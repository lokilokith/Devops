# OpsForge Approval Domain Specification

**Status:** Pending Review

**Scope:** Approval domain only

**Applies to:** Future implementation in `app/approval/` and authorization decision references across the platform

**Out of scope:** SQLAlchemy models, Python code, migrations, repositories, services, APIs, the AccessRequest entity, session brokering, and business service implementations

---

## 1. Executive Summary

The Approval domain is the authorization engine of the OpsForge Privileged Access Management (PAM) platform. It exists solely to record the decisions made regarding an `AccessRequest`. 

Following the Architecture-First methodology, the Approval domain is strictly decoupled from the lifecycle of the request itself. While the AccessRequest domain tracks the *intent* and temporal *state* of a request, the Approval domain records *who* evaluated it, *why* they made their decision, and the *outcome*. This separation guarantees that OpsForge can support complex enterprise workflows—including multi-stage, parallel, sequential, delegated, and automated approvals—without ever requiring a redesign of the core request schema.

---

## 2. Business Purpose

In enterprise PAM, the rules governing who is allowed to approve a privileged session are complex and highly variable. They depend on risk levels, compliance mandates, and organizational structures. 

The Approval domain provides a standardized, immutable ledger of authorization decisions. By abstracting the decision into its own domain, OpsForge can easily pivot between simple one-step manager approvals and complex, multi-tiered approval chains without breaking operational continuity. It guarantees that every access decision is highly auditable and structurally sound.

---

## 3. Responsibilities

- Recording individual authorization decisions (`Approved`, `Rejected`, `Delegated`, etc.).
- Tracking multi-stage workflows (parallel and sequential) using logical grouping.
- Enforcing the segregation of duties (e.g., a requester cannot be their own approver).
- Storing the identity of the decider (User, Role, or automated Policy Engine).
- Capturing the justification or comments provided at the time of the decision.
- Notifying the AccessRequest domain when a workflow reaches a consensus (either fully approved or immediately rejected).

---

## 4. Out-of-Scope Responsibilities

- **Request Lifecycle:** Approval does not own the AccessRequest state. It signals the outcome, but the AccessRequest manages its own transitions to `Active` or `Expired`.
- **Session Management:** Approval does not execute the access or manage broker connections.
- **Credential Handling:** Approval does not interact with vaults or secret stores.
- **Resource Definition:** Approval does not care what the target is, only that it is evaluating an `access_request_id`.
- **Identity Provider Integration:** Approval defers identity routing to the User and Role domains.

---

## 5. DDD Boundary Statement

Approval is a core domain entity in the `approval` bounded context. It strictly owns the decision record, the stage/sequence of the evaluation, the identity of the evaluator, and the decision payload (status and comments). It does not own the intent of the request, the lifecycle of the user, or the physical provisioning of access.

---

## 6. Approval Lifecycle

The lifecycle defines the state of a specific, individual decision step within an access request's workflow.

### 6.1 Valid States
- **Pending:** Awaiting a decision from the assigned approver (User or Role).
- **Approved:** The assigned approver authorized the request step. (Terminal for this record)
- **Rejected:** The assigned approver denied the request step. (Terminal for this record)
- **Cancelled:** The decision step was aborted (e.g., because the overall AccessRequest was canceled, or a parallel approver rejected it, short-circuiting the workflow). (Terminal for this record)
- **Expired:** The time allowed for the approver to make a decision (defined by `decision_deadline`) elapsed. (Terminal for this record)
- **Delegated:** The assigned approver reassigned the decision to another entity, spawning a new Approval record. (Terminal for this record)

### 6.2 State Transition Constraints
- An Approval record is completely immutable once it reaches a terminal state (`Approved`, `Rejected`, `Cancelled`, `Expired`, `Delegated`).
- A `Pending` approval cannot be skipped; it must transition to a terminal state to preserve the audit trail.

---

## 7. Relationships

### 7.1 Relationship with AccessRequest
**Cardinality:** Many-to-One (Many Approvals belong to one AccessRequest)
- The Approval entity holds the `access_request_id`.
- Multiple Approvals can exist for a single request to support multi-stage workflows.

### 7.2 Relationship with User (Approver)
**Cardinality:** Many-to-One
- `approver_user_id` explicitly identifies the human who made the decision.

### 7.3 Relationship with Role (Approval Queue)
**Cardinality:** Many-to-One
- `target_role_id` defines if an approval is assigned to a group (e.g., "Security Admins") rather than a specific individual. Any User holding this Role can claim and execute the approval, setting their `approver_user_id` at the moment of decision.

### 7.4 Relationship with AuditLog
**Cardinality:** One-to-Many
- Every state transition must generate an immutable AuditLog record referencing the `approval_id`.

### 7.5 Relationship with Policy Engine (Reference Only)
**Cardinality:** Many-to-One
- `approval_policy_id` acts as an immutable reference to the specific workflow or policy rule that mandated this approval step. This decouples the Approval record from the actual policy logic while providing a deterministic audit trail of *why* the approval was required.

---

## 8. Attribute Definitions

| Attribute | Purpose | Type | Required | Mutable | Default | Validation Rules |
|---|---|---|:---:|:---:|---|---|
| id | Primary business key | UUID v4 | Yes | No | Generated | Immutable |
| access_request_id | The request being evaluated | UUID v4 | Yes | No | None | Must reference a valid AccessRequest |
| approval_policy_id | Reference to the governing workflow rule | UUID v4 | Yes | No | None | Immutable pointer to the policy that required this approval |
| target_user_id | Specifically assigned approver | UUID v4 | No | No | Null | Either `target_user_id` or `target_role_id` must be set |
| target_role_id | Group assigned approver | UUID v4 | No | No | Null | Mutually exclusive or fallback for `target_user_id` |
| approver_user_id | The actual user who made the decision | UUID v4 | No | Yes | Null | Set when decision is made; must not be the requester |
| stage | Sequence identifier | Integer | Yes | No | 1 | Approvals with the same stage are parallel; increasing stages are sequential |
| status | Lifecycle state | Enum | Yes | Yes | `pending` | Must follow valid state machine transitions |
| comments | Justification for decision | String | No | Yes | Null | Immutable once status is terminal |
| decision_deadline | Expiration time for this approval step | Timestamp | Yes | No | None | Immutable UTC. System auto-expires record if elapsed |
| decision_at | Timestamp of the evaluation | Timestamp | No | Yes | Null | Set automatically upon terminal status transition |
| created_at | Creation timestamp | Timestamp | Yes | No | Auto | Immutable UTC |
| updated_at | Modification timestamp | Timestamp | Yes | No | Auto | Updates on persisted change |

---

## 9. Business Rules

### 9.1 Multi-Stage & Parallel Approvals
- **Parallel:** Multiple Approval records with the same `stage` integer operate concurrently. The governing policy (referenced by `approval_policy_id`) dictates if 1-of-N or M-of-N is required to clear the stage.
- **Sequential:** Approval records with a higher `stage` integer remain `Pending` (or are dynamically generated) only after all required approvals in the lower `stage` are `Approved`.

### 9.2 Segregation of Duties
- The `approver_user_id` must NEVER match the `requester_user_id` of the parent AccessRequest. The system must hard-block self-approval.

### 9.3 Delegation and Escalation
- When an approver selects `Delegated`, a new Approval record is generated pointing to the delegated User/Role, preserving the original record as an audit trail of the delegation action.

### 9.4 Short-Circuiting
- If any required Approval record transitions to `Rejected`, the parent AccessRequest is instantly `Rejected`, and all other `Pending` approvals for that request are immediately marked as `Cancelled`.

### 9.5 Break-Glass / Emergency Access
- Emergency access creates an Approval record that is instantly transitioned to `Approved` by a System/Policy actor, accompanied by mandatory high-priority audit events and post-incident review requirements.

---

## 10. Validation Strategy

### 10.1 Database Validation
- `id` is primary key.
- Foreign keys enforced for `access_request_id`, `target_user_id`, `target_role_id`, and `approver_user_id`.
- Required fields have `NOT NULL` constraints.
- `target_user_id` and `target_role_id` must have a CHECK constraint ensuring at least one is NOT NULL.

### 10.2 Application Validation
- `stage` must be an integer >= 1.
- Terminal states lock the `comments`, `approver_user_id`, and `status` fields against further modification.

### 10.3 Business Validation
- Ensure `approver_user_id` does not match the parent request's `requester_user_id`.
- Ensure `approver_user_id` is an `Active` User in the platform.

### 10.4 Authorization Validation
- Only the assigned `target_user_id` or a User possessing the `target_role_id` is authorized to transition an Approval record from `Pending` to a terminal state.

---

## 11. Security Considerations

- **Non-Repudiation:** The `approver_user_id` and `decision_at` fields create a legally auditable trail of exactly who authorized access and when.
- **Immutability:** Once an approval decision is made, the record cannot be altered, ensuring that compromised admins cannot rewrite history to hide malicious access approvals.
- **Isolation:** By isolating this domain from the request intent, an attacker who manages to spoof a request still has to successfully compromise the independent Approval workflow to gain access.

---

## 12. Audit Expectations

The following events must be logged to the AuditLog domain:
- Approval record created (workflow initialized)
- Approval decision made (Approved/Rejected)
- Approval delegated (including the delegator and the new target)
- Approval expired (SLA missed)
- Break-glass policy executed (Emergency override)

---

## 13. Future Compatibility

This schema supports massive future extensibility without redesign:
- **Policy Engines:** A future automated policy engine can simply write an Approval record with an `approver_user_id` representing the "System Policy Actor" or a specific `policy_id` metadata attribute.
- **ServiceNow/Jira Integration:** ITSM webhook responses can fulfill a `Pending` Approval record via API, translating a Jira ticket approval into an OpsForge approval perfectly.
- **Risk Scoring:** An AI or risk-engine can inject dynamic approval stages (e.g., forcing a CISO approval stage if a request breaches a risk threshold) because the `stage` sequence is infinitely expandable.

---

## 14. Architecture Self-Review

### 14.1 Constraint Checks
- **Independence:** Approval strictly records decisions and does not own the AccessRequest lifecycle. (Pass)
- **Workflows:** Parallel, sequential, delegation, and escalation are natively supported via the `stage` and `target_role_id` constructs. (Pass)
- **No Implementation:** Document strictly focuses on DDD boundaries, attributes, and constraints without ORM syntax. (Pass)

### 14.2 Simplification Review
By leveraging a single, generic `Approval` entity with `stage` ordering and Role/User targeting, the system avoids complex hard-coded workflow schemas. The domain handles simple 1-step approvals exactly the same way it handles complex 5-tier dynamic workflows, ensuring extreme scalability.

### 14.3 Final Assessment
The Approval domain provides a robust, enterprise-grade authorization engine. It guarantees segregation of duties, non-repudiation, and structural immutability while maintaining a loose coupling with the AccessRequest intent, strictly adhering to PAM best practices.

**Recommendation:** PENDING ARCHITECTURE REVIEW -> READY FOR APPROVAL

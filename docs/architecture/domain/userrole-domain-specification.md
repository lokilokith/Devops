# OpsForge UserRole Domain Specification

**Status:** Frozen design contract

**Scope:** UserRole association domain only (owned by the `roles` bounded context)

**Applies to:** Future implementation in `app/roles/` and related integration points

**Out of scope:** SQLAlchemy models, Python code, migrations, repositories, services, APIs, auditing implementation, session management, or authorization policy logic

---

## 1. Purpose

The `UserRole` domain concept defines the authoritative many-to-many membership association between a `User` (local human account) and a `Role` (application authorization category). It acts as the explicit, auditable bridge that grants a specific role to a specific user, recording when the assignment occurred and who authorized it.

## 2. Responsibilities

- **Enforce Membership:** Reliably map a single user to one or more roles, and a single role to one or more users.
- **Prevent Duplication:** Guarantee that a user cannot be assigned the same role more than once simultaneously.
- **Track Provenance:** Record the administrative `assigned_by` identity and the `assigned_at` timestamp for security and auditing purposes.
- **Support Lifecycle Logic:** Act as the foundation for granting and revoking access without deleting historical accountability.

## 3. Scope

The UserRole domain is strictly scoped to the *assignment* of roles. It lives within the `roles/` bounded context because it governs who holds a given role. It does not govern the identity of the user, nor does it enforce what a role can do (permissions).

## 4. Out-of-Scope Responsibilities

- **Authorization Enforcement:** UserRole does not evaluate whether a user can perform an action; it only provides the membership data for a policy engine to evaluate.
- **Identity Management:** UserRole does not manage user lifecycle states (e.g., active, suspended).
- **Audit Logging:** UserRole triggers audit events but does not own the `AuditLog` domain.
- **Denormalized Storage:** UserRole must remain a normalized association entity and not be flattened into a JSON array on the `User` or `Role` entities.

## 5. Domain Concepts

| Concept | Meaning |
|---|---|
| **Membership** | The active state of a user holding a role. |
| **Assignment** | The act of creating a membership. |
| **Revocation** | The act of terminating a membership. |
| **Provenance** | The historical record of *who* authorized the assignment (`assigned_by_user_id`). |

## 6. UserRole Lifecycle

The UserRole lifecycle is uniquely brief because it acts as an associative link:

- **Assigned:** The user holds the role.
- **Revoked:** The user no longer holds the role.

*Note on Revocation:* In OpsForge V1, revocation may involve physical deletion of the association row for simplicity, provided that an immutable `AuditLog` captures the revocation event. The `UserRole` table itself does not use soft delete (`deleted_at`) or a `status` Enum. 

## 7. Business Rules

1. A User may hold multiple roles simultaneously.
2. A Role may be assigned to multiple users simultaneously.
3. A specific User-Role combination must be strictly unique (no duplicate assignments).
4. A role cannot be assigned to a `User` whose lifecycle state is `archived` (and typically not if `disabled`).
5. A role assignment cannot use a `Role` whose lifecycle state is `retired` or `inactive`.
6. The `assigned_by_user_id` must reference an active administrator at the time of assignment, or be null if the assignment is system-generated (e.g., during bootstrapping).
7. If a role is retired, existing memberships should be evaluated by the service layer, but the historical assignment records must not be orphaned or cascaded away unintentionally.

## 8. Validation Rules

### 8.1 Database Constraints
- **Composite Primary Key:** `user_id` and `role_id` must act together as the primary key.
- **Foreign Key Integrity:** `user_id` and `role_id` must reference existing, valid rows.
- **Not Null:** Both `user_id` and `role_id` must be provided.

### 8.2 Application Validation
- The application must verify that the target `User` and `Role` are in operational states before persisting the assignment.

### 8.3 Business Validation
- The system must ensure the executing administrator possesses the necessary privileges to assign or revoke the targeted role.
- Redundant assignments (assigning a role the user already holds) must be caught and gracefully handled (e.g., idempotent success or validation error) before reaching database constraint errors.

## 9. Required Attributes

| Attribute | Conceptual Type | Business Meaning | Default |
|---|---|---|---|
| `user_id` | UUID v4 | Identifies the membership owner. | None |
| `role_id` | UUID v4 | Identifies the assigned role. | None |
| `assigned_at` | Timestamp (UTC) | The exact moment the assignment occurred. | `CURRENT_TIMESTAMP` |

## 10. Optional Attributes

| Attribute | Conceptual Type | Business Meaning | Default |
|---|---|---|---|
| `assigned_by_user_id` | UUID v4 | Identifies the administrator or actor who granted the role. Nullable for system-seeded roles. | Null |

## 11. Relationships

- **Many-to-One with User:** A `UserRole` belongs to exactly one `User`.
- **Many-to-One with Role:** A `UserRole` belongs to exactly one `Role`.
- **Many-to-One with User (Provenance):** A `UserRole` optionally references one `User` as the assigning administrator.

*Note:* UserRole does not interact with `AccessRequest`, `Approval`, or `Resource`. Those domains rely on UserRole indirectly through authorization queries.

## 12. Database Constraints

As per the `domain-database-design-v1.md`, the following foreign key delete behaviors are mandatory:

- `fk_user_roles_users_user_id`: **RESTRICT**. Role membership must not survive the removal of the referenced user through a cascade. (Users should not be deleted, but if they are, it must be restricted).
- `fk_user_roles_roles_role_id`: **RESTRICT**. Role membership history should not vanish if a role is retired or removed.
- `fk_user_roles_users_assigned_by_user_id`: **SET NULL**. Assignment provenance is useful, but the membership row must remain valid even if the assigning admin is eventually hard-deleted.

## 13. Index Strategy

High-value indexes must be placed to support both directions of membership queries:
- `user_id` must be indexed (to quickly find all roles for a user).
- `role_id` must be indexed (to quickly find all users holding a specific role).
- `assigned_by_user_id` must be indexed to support audits of administrative actions.
- `assigned_at` must be indexed to support temporal querying and audit reviews.

*(Note: The composite primary key implicitly covers indexing for `user_id`, but explicit indexing ensures performant reverse lookups for `role_id`).*

## 14. Security Considerations

- **Least Privilege:** Assignment logic must be strictly gated. Only administrators with explicit role-granting privileges may create or destroy `UserRole` records.
- **Traceability:** Every assignment and revocation is a highly sensitive security event and must be immutably recorded in the `AuditLog`.
- **Orphan Prevention:** The `RESTRICT` database behaviors prevent security holes where a user might maintain privileges to a deleted role ID.

## 15. Audit Expectations

The `AuditLog` domain is separate, but `UserRole` lifecycle events are mandatory triggers. The following events must generate immutable audit logs:
- `role_assigned` (capturing the user, the role, and the assigner)
- `role_revoked` (capturing the user, the role, and the revoker)

## 16. Future Compatibility

- **External Identity Providers (Azure AD, Okta):** If external groups are mapped into OpsForge, the `UserRole` association remains valid. The application layer can synchronize external groups by managing `UserRole` assignment rows.
- **ABAC (Attribute-Based Access Control):** Role assignments remain a fundamental pillar, acting as static attributes in a broader ABAC policy engine.
- **Temporary Role Assignments:** If time-bound roles are introduced in a future version, `UserRole` can easily be extended with `expires_at` without breaking this normalized schema.

## 17. Risks

- **Silent Revocation:** If a `UserRole` row is deleted directly in the database, the application loses the historical membership state unless the `AuditLog` captured it. Mitigation: Restrict direct database access and enforce strict API usage.
- **Stale Provenance:** If an administrator account is deleted, the `SET NULL` behavior removes the provenance link on the `UserRole` row. Mitigation: Ensure the `AuditLog` (which does not cascade) captures the original administrator ID during the `role_assigned` event.

## 18. Testing Strategy

- **Constraint Testing:** Attempt to assign the same role to the same user twice and assert that a unique constraint violation or validation error occurs.
- **Referential Integrity Testing:** Attempt to delete a User or Role that is linked in `UserRole` and assert that a `RESTRICT` error is raised. Attempt to delete an assigning administrator and verify `SET NULL` behavior.
- **Validation Testing:** Attempt to assign a role to an archived user or assign a retired role, asserting business validation rejections.
- **Performance Testing:** Ensure `user_id` and `role_id` reverse lookups scale efficiently with 100,000+ assignment rows.

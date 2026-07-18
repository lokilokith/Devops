# OpsForge Database Conventions

## 1. Purpose

These conventions define how all future SQLAlchemy models and Alembic migrations must be written for OpsForge.

They exist to keep the database layer consistent, maintainable, and easy to reason about as the project grows. Good conventions reduce ambiguity in model definitions, make migrations safer to review, improve onboarding for new contributors, and help the codebase scale without accumulating naming drift or schema debt.

### Why conventions matter

- **Consistency**: Every table, column, key, and relationship follows the same rules.
- **Maintainability**: Changes are easier to review when the schema has predictable structure.
- **Readability**: Future contributors can infer intent from names and patterns.
- **Migration safety**: Clear rules reduce accidental breaking changes.
- **Onboarding**: New contributors can understand the database layer faster.
- **Scalability**: A disciplined schema is easier to evolve as traffic and business rules grow.

## 2. Database Technology

OpsForge uses the following official database stack:

| Layer | Technology | Role |
|---|---|---|
| Production database | PostgreSQL | Primary production data store |
| Development database | SQLite | Local development and lightweight testing |
| ORM | SQLAlchemy 2.x | Data modeling and persistence abstraction |
| Migration tool | Alembic | Schema versioning and upgrade/downgrade management |

### Standards

- PostgreSQL is the source of truth for production behavior.
- SQLite must remain supported for development convenience, but schema design should not depend on SQLite-only behavior.
- SQLAlchemy models must remain portable across both dialects wherever practical.
- Alembic migrations must be written so they can be reviewed and reasoned about independently of application code.

## 3. Primary Key Standards

### Required standard

- All core business tables must use **UUID primary keys**.
- UUID version should be **v4** unless a later standard explicitly changes it.
- Primary keys must be named `id`.

### Why UUIDs instead of integers

- They reduce exposure of sequential row counts.
- They support safer future scaling and distributed generation.
- They are more suitable for replication, import/export, and offline record creation scenarios.
- They avoid unnecessary coupling to insertion order.

### Naming convention

- Primary key column name: `id`
- Foreign key references: `<entity>_id`

### Data type expectations

| Environment | Recommended storage approach |
|---|---|
| PostgreSQL | Native UUID type with UUID-aware ORM mapping |
| SQLite | Portable string-backed UUID representation |

### SQLAlchemy expectations

- ORM models must use a UUID-capable primary key type consistent with the target dialect.
- UUID values must be generated at creation time, not derived from business data.
- Primary keys must never be repurposed as business identifiers.

### Documentation example only

| Entity | Primary key |
|---|---|
| users | `id` |
| roles | `id` |
| resources | `id` |
| access_requests | `id` |
| approvals | `id` |
| audit_logs | `id` |

## 4. Table Naming Convention

### Standard

- Table names must be **lowercase**.
- Table names must use **snake_case**.
- Table names should be **plural**.

### Why plural table names

OpsForge models business collections rather than singular language constructs. Plural names keep the schema aligned with common relational conventions and the approved domain design.

### Rules

- Use plural nouns for entity tables: `users`, `roles`, `resources`, `access_requests`, `approvals`, `audit_logs`.
- Use singular or compound names only for pure join or association tables if needed later, but the default remains plural for all business tables.
- Do not mix singular and plural forms for the same concept.
- Do not use camelCase, PascalCase, or hyphenated names.

### Examples

| Correct | Incorrect |
|---|---|
| `users` | `User` |
| `access_requests` | `accessRequest` |
| `audit_logs` | `auditLog` |
| `user_roles` | `userRole` |

## 5. Column Naming Convention

### Standard

- All columns must use **snake_case**.
- Column names must be descriptive and stable.
- Column names should reflect business meaning, not UI labels.

### Examples

| Correct | Meaning |
|---|---|
| `created_at` | Record creation timestamp |
| `updated_at` | Last update timestamp |
| `deleted_at` | Soft delete timestamp, when used |
| `manager_user_id` | Reference to manager user |
| `requester_user_id` | Reference to requesting user |
| `resource_id` | Reference to resource |

### Rules

- Do not use camelCase.
- Do not abbreviate unless the term is already a standard domain abbreviation.
- Do not introduce two names for the same concept.
- Prefer full clarity over brevity when the tradeoff is small.

## 6. Timestamp Convention

### Required timestamp fields

| Column | Purpose |
|---|---|
| `created_at` | When the record was created |
| `updated_at` | When the record was last modified |
| `deleted_at` | When a soft delete occurred, if soft delete is permitted |

### Rules

- Timestamps must be timezone-aware in application design.
- Canonical stored time must be UTC.
- `created_at` must be set automatically at insert time.
- `updated_at` must change automatically on every update.
- `deleted_at` must be nullable and only used when the entity supports soft delete.

### Expected behavior

- `created_at` is immutable after insertion.
- `updated_at` is managed by the persistence layer and should not rely on manual updates in application code.
- `deleted_at`, when present, marks a logical removal date, not a physical delete.

### Recommendation

Use UTC everywhere. Do not store local time as canonical database time.

## 7. Foreign Key Naming

### Standard

- Foreign key columns must follow the pattern: `<entity>_id`
- Foreign key names must reference the target business entity, not the source table.

### Examples

| Column | Target |
|---|---|
| `role_id` | roles.id |
| `resource_id` | resources.id |
| `manager_user_id` | users.id |
| `requester_user_id` | users.id |
| `approver_user_id` | users.id |

### Rules

- Use the same naming pattern across all tables.
- If multiple foreign keys point to the same target table, use role-based names for clarity.
- Avoid generic names such as `user_id_1` or `ref_id`.

## 8. Relationship Naming

Relationship property names in SQLAlchemy models must match the business meaning of the link.

### Naming guidance

- Use **singular** names for many-to-one or one-to-one relationships.
- Use **plural** names for one-to-many or many-to-many collections.
- Use role-specific names when a table has multiple relationships to the same entity.

### Examples

| Relationship direction | Recommended property name |
|---|---|
| user -> role membership | `user.roles` |
| role -> user membership | `role.users` |
| resource -> access requests | `resource.requests` |
| access request -> approvals | `request.approval` or `request.approvals` depending on cardinality |
| approval -> access request | `approval.request` |

### Rules

- Relationship names must be intuitive and consistent with the domain.
- Do not name relationships after table internals when a business name exists.
- Do not use the same name for both a scalar relationship and a collection relationship.

## 9. Constraint Naming Convention

All database constraints must use predictable names.

### Standard patterns

| Constraint type | Pattern | Example |
|---|---|---|
| Primary key | `pk_<table>` | `pk_users` |
| Foreign key | `fk_<source>_<target>` | `fk_users_roles` |
| Unique constraint | `uq_<table>_<column>` | `uq_users_email` |
| Check constraint | `ck_<table>_<rule>` | `ck_access_requests_dates` |
| Index | `ix_<table>_<columns>` | `ix_access_requests_status` |

### Why predictable names matter

- They make Alembic diffs easier to read.
- They reduce ambiguity during troubleshooting.
- They make rollback and refactor work safer.
- They improve cross-team communication when discussing schema changes.

### Rules

- Constraint names must be deterministic and stable.
- Constraint names should not depend on autogenerated database naming that differs by dialect.
- New migrations must preserve existing constraint names whenever possible.

## 10. Index Convention

### General principles

Indexes should be created for real query patterns, not by default.

### When to add indexes

- On primary lookup columns such as emails, usernames, and request codes.
- On foreign keys that are frequently joined or filtered.
- On status columns used in operational queues.
- On composite filters that appear together in common queries.
- On time-based columns when they are part of a common filter pattern.

### When not to add indexes

- On columns that are rarely filtered.
- On low-cardinality columns that will not improve selectivity.
- On every timestamp column by default.
- On fields that are only used for display or long-text content.

### Examples

| Index type | Example | Why |
|---|---|---|
| Single-column | `users.email` | Fast identity lookup |
| Single-column | `users.username` | Login and admin lookup |
| Composite | `(access_requests.requester_user_id, access_requests.status)` | Common queue filter |
| Composite | `(access_requests.resource_id, access_requests.status)` | Resource-focused review |
| Composite | `(audit_logs.subject_type, audit_logs.subject_id, audit_logs.occurred_at)` | Subject-scoped audit review |

### Rules

- Prefer composite indexes over many single-column indexes when the query pattern is multi-column.
- Do not add redundant indexes that duplicate the same access path.
- Revisit indexes after query patterns are known, but do not wait for production pain when the pattern is obvious.

## 11. Enum Convention

### Python Enum usage

- Python enums should define controlled business vocabularies.
- Enum names must be descriptive and domain-oriented.
- Enum values should be stable and suitable for persistence.

### Database Enum usage

- Use database-backed enums only when the dialect and migration strategy support them cleanly.
- For portability, string columns with application validation may be preferred when the value set is small and stable.

### Naming style

- Enum class names should be singular and descriptive: `UserStatus`, `RoleType`, `AccessRequestStatus`.
- Enum values should be lowercase and stable unless the domain requires a different convention.

### Future extensibility

- Enum growth must remain backward compatible.
- Removing or renaming an enum value is a breaking change and must be treated carefully.
- When a vocabulary is expected to grow substantially, consider whether a lookup table is more appropriate in a future version.

## 12. Soft Delete Policy

### Standard

Soft delete uses `deleted_at`.

### Rules

- Soft delete is allowed only when business history may still be useful after removal from active views.
- Soft delete must never be used as a substitute for proper status management when a record has meaningful lifecycle states.
- Soft delete must not be used for audit logs or other immutable records.

### When records should be soft deleted

- Only for entities where the business requirement is to hide a record from active use while preserving it for reference.
- Only when the record does not need to remain operationally active.

### When records should never be deleted

- Audit logs.
- Historical approval decisions.
- Historical access request records.
- Any record that must remain as evidence or compliance history.

### Audit implications

- Soft delete changes must themselves be auditable.
- Soft delete does not erase history; it only changes visibility or lifecycle state.
- If an entity is soft deleted, the system should still be able to explain why it exists historically.

## 13. Cascade Policy

### Supported behaviors

| Action | Meaning | Typical use |
|---|---|---|
| `CASCADE` | Delete dependent records automatically | Rare, only for purely dependent child data |
| `RESTRICT` | Block deletion when dependents exist | Default for business-critical records |
| `SET NULL` | Preserve child record and null the FK | Useful for optional provenance links |
| `NO ACTION` | Defer enforcement to database behavior | Acceptable when behavior is intentionally strict |

### Guidance

- Use `RESTRICT` for core business entities that must not disappear if referenced.
- Use `SET NULL` only when the child record must survive but the relationship is optional.
- Use `CASCADE` sparingly and only for truly dependent records that have no independent business value.
- Use `NO ACTION` only when the exact database behavior is understood and intentionally chosen.

### OpsForge expectations

- Historical records should generally be preserved.
- Audit evidence must not be removed by cascading deletes.
- Ownership, approval, and request history should remain intact.

## 14. Audit Data Policy

Audit data is immutable.

### Rules

- Audit logs must never be updated.
- Audit logs must never be deleted.
- Audit logs must be append-only.
- Audit logs must capture actor, subject, event, timestamp, and meaningful context.

### Retention expectations

- Audit data should be retained according to the project’s operational and compliance requirements.
- Retention policies may be enforced outside the application, but the application must not undermine them.
- Audit data should be treated as long-lived evidence.

### Guidance

- Do not store audit data in a way that makes it easy to tamper with history.
- Treat audit tables as write-once operational records.
- If external archival is introduced later, the source of truth remains immutable.

## 15. Migration Rules

### Required standards

- One logical schema change per migration whenever practical.
- Migration names must be clear, specific, and reviewable.
- Every migration must be reviewed before merge.
- Rollback behavior must be understood before a migration is accepted.
- Executed migrations must never be edited.

### Guidance

- Keep migrations small and understandable.
- Avoid combining unrelated schema changes into one revision.
- Treat migration history as a permanent record.
- If a migration is wrong after execution, create a new corrective migration rather than rewriting history.

## 16. SQLAlchemy Standards

### Model design

- Use declarative ORM models.
- Use typed ORM declarations where supported by the codebase standard.
- Keep models aligned with the frozen domain design.
- Keep model names and table names consistent with the conventions in this document.

### Relationship standards

- Model relationships must reflect real database cardinality.
- Use singular relationship names for single targets.
- Use plural relationship names for collections.
- Avoid bidirectional relationships unless both directions are useful.
- Avoid unnecessary relationship depth if the query path does not need it.

### Loading strategy

- Default loading strategy should be chosen deliberately, not accidentally.
- Eager loading should be used when the access pattern is known and repeated.
- Lazy loading should not create hidden performance problems.
- Guard against N+1 query patterns in the service and repository layers.

### Naming consistency

- Model class names should remain business-oriented and singular.
- Table names should remain plural and snake_case.
- Relationship names and foreign key names should follow the same domain vocabulary.

## 17. Validation Philosophy

Validation should happen at multiple layers, with each layer responsible for a different class of correctness.

### Database constraints

Database constraints should enforce invariants that the database can reliably guarantee:

- primary keys
- unique constraints
- foreign keys
- check constraints
- not-null rules

### Application validation

Application validation should handle user-facing input quality and workflow-aware checks such as:

- request reason length
- state-transition eligibility
- approval eligibility
- manager snapshot resolution
- role assignment permissions

### Business rule validation

Business rules should enforce the domain policy and workflow behavior that spans multiple fields or entities.

### Rule of thumb

- If the database can reliably enforce it, enforce it there.
- If it is a data-quality rule, validate it in the application.
- If it is a workflow or policy rule, validate it in the business layer and back it up with constraints where possible.

## 18. Performance Considerations

### Indexes

- Index the queries you expect to run frequently.
- Prefer selective indexes and useful composites.
- Avoid unnecessary write overhead from too many indexes.

### Query optimization

- Load only the data needed for the current use case.
- Avoid unnecessary joins.
- Keep query shapes predictable.
- Use pagination for list endpoints and administrative views.

### N+1 prevention

- Watch for N+1 query patterns when loading related data.
- Use deliberate loading strategies for collections that are rendered together.
- Measure before optimizing excessively.

### Future scaling

- Partitioning may be considered later for very large append-only tables such as audit logs.
- Sharding is not a Version 1 requirement and should not be assumed.
- Design the schema so later scaling options remain open, but do not add complexity prematurely.

## 19. Security Considerations

### Least privilege

- Application database users should have only the permissions they need.
- Operational roles should not have broad destructive access.
- Audit data should be protected from casual modification.

### Sensitive data

- Do not store secrets in ordinary business tables.
- Do not store credentials where they can be casually queried.
- Classify sensitive fields carefully and minimize exposure.

### Auditability

- Security-sensitive actions should be traceable.
- Important state transitions should create audit evidence.
- History should be explainable after the fact.

### Immutable history

- Historical decisions and audit records must remain trustworthy.
- Avoid schema or application behavior that makes it easy to erase the trail.

### Encryption considerations

- Sensitive fields should be protected according to the project’s security posture.
- Encryption strategy should be explicit for any field that later stores credentials, tokens, or highly sensitive identifiers.
- Encryption at rest in the database environment should be assumed as part of the platform baseline, not as a substitute for good schema design.

## 20. Future Guidelines

### New entities

- New entities must follow the naming, key, and timestamp conventions in this document.
- New entities must be justified by business need, not speculative complexity.
- New entities should fit the approved domain architecture.

### New relationships

- New relationships must reflect real business meaning.
- Cardinality must be documented before implementation.
- Foreign key behavior must be defined before merge.

### Versioning

- Schema changes must preserve the ability to understand historical records.
- Breaking changes must be treated carefully and documented.
- Prefer additive evolution over disruptive redesign.

### Schema evolution

- Keep migrations reversible where practical.
- Introduce new columns before removing old behavior.
- Avoid renaming or dropping schema elements without a clear migration path.

### Backward compatibility

- Existing data and migrations must remain understandable after future changes.
- Do not assume a clean data reset is acceptable.
- Future versions should preserve the enterprise history already recorded.

---

## Summary

This document is the official database engineering standard for OpsForge. All future SQLAlchemy models and Alembic migrations must follow these conventions unless a later approved standards update changes them.

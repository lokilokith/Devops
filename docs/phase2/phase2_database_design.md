# Phase 2 Database Design

This document outlines the required schema additions and modifications to support Phase 2 PAM features.

## 1. privileged_access_sessions
**Purpose:** Tracks temporary privileged access grants and active sessions.
- `id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key -> `users.id`)
- `resource_id` (UUID, Foreign Key -> `resources.id`)
- `access_request_id` (UUID, Foreign Key -> `access_requests.id`)
- `status` (Enum: PENDING, ACTIVE, TERMINATED, EXPIRED)
- `started_at` (Timestamp)
- `expires_at` (Timestamp)
- `terminated_at` (Timestamp, Nullable)
- `recording_url` (String, Nullable)
**Indexes:** `user_id`, `resource_id`, `status`

## 2. session_events
**Purpose:** Tracks granular actions within a privileged session.
- `id` (UUID, Primary Key)
- `session_id` (UUID, Foreign Key -> `privileged_access_sessions.id`)
- `event_type` (String)
- `event_data` (JSONB)
- `timestamp` (Timestamp)
**Indexes:** `session_id`, `timestamp`

## 3. access_policies
**Purpose:** Stores dynamic authorization rules for JIT and ABAC.
- `id` (UUID, Primary Key)
- `name` (String, Unique)
- `description` (String)
- `conditions` (JSONB - stores IP restrictions, time-of-day, etc.)
- `max_duration_seconds` (Integer)
- `requires_approval` (Boolean)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)
**Indexes:** `name`

## 4. secret_rotation_policies
**Purpose:** Configures automatic lifecycle and rotation for vault secrets.
- `id` (UUID, Primary Key)
- `vault_item_id` (UUID, Foreign Key -> `vault_items.id`)
- `rotation_interval_seconds` (Integer)
- `last_rotated_at` (Timestamp)
- `next_rotation_at` (Timestamp)
- `rotation_script_id` (UUID, Foreign Key to script definitions)
- `status` (Enum: ACTIVE, PAUSED, ERROR)
**Indexes:** `vault_item_id`, `next_rotation_at`

## 5. compliance_reports
**Purpose:** Stores generated security and compliance reports.
- `id` (UUID, Primary Key)
- `report_type` (Enum: SOC2, ISO27001, CUSTOM)
- `generated_by` (UUID, Foreign Key -> `users.id`)
- `generated_at` (Timestamp)
- `report_url` (String)
- `parameters` (JSONB)
**Indexes:** `generated_at`, `report_type`

## Migration Strategy
- Migrations will be strictly additive. No existing columns or tables from Phase 1 will be dropped.
- Phase 2 features will use separate migration versions.
- Background jobs will be introduced to backfill any default policy assignments for existing resources.

## Rollback Strategy
- Ensure `down` revisions in Alembic correctly drop new tables and remove any ENUM types introduced.
- Application code will be designed to handle missing Phase 2 tables gracefully if rolled back, falling back to Phase 1 static RBAC.

## Data Integrity Rules
- `session_events` cannot be modified or deleted once written (append-only).
- A `privileged_access_sessions` record cannot have its `expires_at` extended beyond the maximum duration defined in the related `access_policies`.

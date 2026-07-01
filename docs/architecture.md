# Architecture Blueprint - OpsForge System Architecture

This document describes the architectural layout, entity specifications, repository design, and business layer workflows in OpsForge.

---

## Data Access Architecture Flow

The persistence architecture follows the **Repository Pattern** to separate data access logic from core business services:

```text
Service Layer (Manages Transactions & Transitions)
       ↓
Repository Layer (Encapsulates SQLAlchemy queries)
       ↓
Model Layer (Defines database schema, indices, enums)
       ↓
PostgreSQL / SQLite Database
```

---

## 1. Threat Entity Specification

The `Threat` database model is declared in [app/models/threat.py](file:///l:/DOWNLOADS/Devops/opsforge/app/models/threat.py) and maps to the `threats` table.

### Fields and Schema Definition

* **`id`**: `Integer` (Primary Key, Auto-increment).
* **`indicator`**: `String(255)` (Indexed, Not Null) — The IP address, domain name, file hash, or URL identifier.
* **`indicator_type`**: `Enum` (Not Null) — Must be one of: `ip`, `domain`, `hash`, `url`.
* **`threat_level`**: `Enum` (Indexed, Not Null) — Must be one of: `low`, `medium`, `high`, `critical`.
* **`confidence`**: `Integer` (Not Null) — Numeric score between `0` and `100`.
* **`mitre_attack`**: `String(50)` (Nullable) — MITRE ATT&CK technique reference ID (e.g. `T1078`).
* **`source`**: `String(100)` (Not Null) — Source feed or analyst team reporting the indicator.
* **`analyst_notes`**: `Text` (Nullable) — Diagnostic commentary or analyst findings.
* **`assigned_analyst`**: `String(100)` (Nullable) — Username of the assigned responder.
* **`status`**: `Enum` (Indexed, Not Null, Default: `Open`) — Must be one of: `Open`, `Investigating`, `Contained`, `Closed`, `False Positive`.
* **`tags`**: `JSON` (Nullable) — Array of tags for categorization (e.g., `["apt", "ransomware"]`).
* **`first_seen`**: `DateTime(timezone=True)` (Nullable) — Earliest time indicator was logged.
* **`last_seen`**: `DateTime(timezone=True)` (Nullable) — Most recent activity timestamp.
* **`created_at`**: `DateTime(timezone=True)` (Indexed, Not Null) — Timestamp of creation, populated automatically.
* **`updated_at`**: `DateTime(timezone=True)` (Not Null) — Timestamp of last modification, updated automatically.

### Database Indexing Strategy
To optimize search performance and range queries for dashboards, indices are placed on:
- `indicator` (Frequent lookup index)
- `status` (Queue filtering)
- `threat_level` (Triage sorting)
- `created_at` (Timeline queries)

---

## 2. Repository Layer Design

The repository is defined in [app/repositories/threat_repository.py](file:///l:/DOWNLOADS/Devops/opsforge/app/repositories/threat_repository.py).

### Core Responsibilities
- **Data Access Encapsulation**: Translates high-level query needs into database-specific SQLAlchemy query commands.
- **Strict Separation of Concerns**: The repository performs queries and CRUD operations but does not manage transactions (no `db.session.commit()` or `db.session.rollback()`) and implements zero business validations.
- **Unification**: All domain-specific data operations flow through this interface.

### Method Signatures
- **`create(threat: Threat) -> Threat`**: Adds a new threat to the database context.
- **`find_by_id(threat_id: int) -> Threat`**: Fetches a single record by primary key.
- **`find_all() -> list[Threat]`**: Fetches all threat records.
- **`find_by_status(status: str) -> list[Threat]`**: Filters threats by status.
- **`find_by_indicator_type(indicator_type: str) -> list[Threat]`**: Filters threats by indicator type.
- **`search(query_str: str) -> list[Threat]`**: Partial match text search on indicators or sources.
- **`update(threat: Threat) -> Threat`**: Adds an updated threat object to the current session.
- **`delete(threat: Threat) -> None`**: Marks a threat record for deletion.
- **`count() -> int`**: Counts total threat records.
- **`paginate(filters: dict, page: int, limit: int, sort: str, order: str) -> Pagination`**: Handles filtered, sorted, windowed offsets.

---

## 3. Business Layer & Service Orchestration

The service layer is defined in [app/services/threat_service.py](file:///l:/DOWNLOADS/Devops/opsforge/app/services/threat_service.py).

### Core Responsibilities
- **Business Logic & Validations**: Enforces domain validations (e.g. confidence ratings bounded to 0-100, indicator type checks) before records are sent to the persistence layer.
- **Workflow State Control**: Enforces the **Threat Status State Machine**, validating transition paths. Illegal paths are rejected with custom exceptions.
- **Transaction Management**: Owns transaction boundaries (`db.session.commit()` and `db.session.rollback()`). If an operation fails, the transaction is rolled back and a `DatabaseOperationException` is raised.
- **Metrics Assembly**: Orchestrates query counts to compute operational dashboard statistics.

### Workflow State Transitions
The system enforces a strict state machine path:
- **`Open ──> Investigating`**
- **`Investigating ──> Contained`** or **`False Positive`**
- **`Contained ──> Closed`**
- **`False Positive ──> Closed`**
- *All other paths (including re-opening a Closed threat) are rejected with an `InvalidStatusTransition` error.*

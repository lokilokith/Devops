# API Design Specification - OpsForge Phase 1

This document specifies the Threat Intelligence Management API endpoints, serialization contracts, data validation models, and architectural routing flow.

---

## Architecture Flow

The application enforces a unidirectional boundary separation pattern to isolate transportation from business rules and persistence operations:

```text
Client Request (HTTP JSON)
         ↓
CustomApi Routing (Flask-RESTX namespaces)
         ↓
Request Serialization & Verification (reqparse / fields validation)
         ↓
ThreatService Business Layer (Validations, State Transitions, and db.session boundary)
         ↓
ThreatRepository Persistence Interface (SQLAlchemy queries and pagination)
         ↓
PostgreSQL / SQLite Database
```

---

## Endpoint Specification

### 1. Threats Namespace (`/threats`)

#### `POST /threats` (Create Threat indicator)
Creates a new validated Threat intelligence record.
- **Request Headers**: `Content-Type: application/json`
- **Request Payload Example**:
```json
{
  "indicator": "185.190.140.10",
  "indicator_type": "ip",
  "threat_level": "critical",
  "confidence": 98,
  "mitre_attack": "T1078",
  "source": "SOC Alert",
  "analyst_notes": "Suspicious login attempt",
  "assigned_analyst": "analyst_bob",
  "tags": ["apt", "compromise"]
}
```
- **Response Payload Example (201 Created)**:
```json
{
  "success": true,
  "message": "Threat created successfully",
  "data": {
    "id": 1,
    "indicator": "185.190.140.10",
    "indicator_type": "ip",
    "threat_level": "critical",
    "confidence": 98,
    "mitre_attack": "T1078",
    "source": "SOC Alert",
    "analyst_notes": "Suspicious login attempt",
    "assigned_analyst": "analyst_bob",
    "status": "Open",
    "tags": ["apt", "compromise"],
    "first_seen": null,
    "last_seen": null,
    "created_at": "2026-07-01T10:00:00+00:00",
    "updated_at": "2026-07-01T10:00:00+00:00"
  }
}
```

#### `GET /threats` (List Threat indicators)
Fetches threat records matching optional filters, supporting pagination and sorting.
- **Query Parameters**:
  - `page`: Page number (default: `1`)
  - `limit`: Items per page (default: `20`)
  - `sort`: Sorting field (default: `created_at`)
  - `order`: Sorting order (`asc` or `desc`, default: `desc`)
  - `status`: Filter by status
  - `indicator_type`: Filter by type
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "Threats retrieved successfully",
  "data": {
    "items": [
      {
        "id": 1,
        "indicator": "185.190.140.10",
        "indicator_type": "ip",
        "threat_level": "critical",
        "confidence": 98,
        "mitre_attack": "T1078",
        "source": "SOC Alert",
        "analyst_notes": "Suspicious login attempt",
        "assigned_analyst": "analyst_bob",
        "status": "Open",
        "tags": ["apt", "compromise"],
        "first_seen": null,
        "last_seen": null,
        "created_at": "2026-07-01T10:00:00+00:00",
        "updated_at": "2026-07-01T10:00:00+00:00"
      }
    ],
    "page": 1,
    "limit": 20,
    "total": 1,
    "pages": 1
  }
}
```

#### `GET /threats/search` (Search Threat indicators)
Searches threat intelligence records by partial indicator or source match.
- **Query Parameters**:
  - `query`: The search pattern (Required)
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "Search results retrieved successfully",
  "data": {
    "items": [
      {
        "id": 1,
        "indicator": "phishing-bank.net",
        "indicator_type": "domain",
        "threat_level": "high",
        "confidence": 85,
        "source": "feed_source",
        "status": "Open",
        "tags": []
      }
    ],
    "page": 1,
    "limit": 1,
    "total": 1,
    "pages": 1
  }
}
```

#### `GET /threats/<id>` (Read Threat indicator)
Retrieves a specific Threat intelligence record.
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "Threat retrieved successfully",
  "data": {
    "id": 1,
    "indicator": "185.190.140.10",
    "indicator_type": "ip",
    "threat_level": "critical",
    "confidence": 98,
    "mitre_attack": "T1078",
    "source": "SOC Alert",
    "analyst_notes": "Suspicious login attempt",
    "assigned_analyst": "analyst_bob",
    "status": "Open",
    "tags": ["apt", "compromise"],
    "first_seen": null,
    "last_seen": null,
    "created_at": "2026-07-01T10:00:00+00:00",
    "updated_at": "2026-07-01T10:00:00+00:00"
  }
}
```

#### `PUT /threats/<id>` (Update Threat indicator)
Updates all fields of an existing threat indicator.
- **Request Payload Example**: Same as POST.
- **Response Payload Example (200 OK)**: Standard Threat JSON wrapper with `message: "Threat updated successfully"`.

#### `PATCH /threats/<id>/status` (Change status)
Updates only the status field, enforcing transitions via the Threat Status State Machine.
- **Request Payload**:
```json
{
  "status": "Investigating",
  "assigned_analyst": "analyst_bob"
}
```
- **Response Payload Example (200 OK)**: Standard Threat JSON wrapper with updated status and assignment values.

#### `DELETE /threats/<id>` (Delete Threat indicator)
Purges a threat intelligence record from the database.
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "Threat with ID 1 deleted successfully",
  "data": {}
}
```

---

### 2. Statistics Namespace (`/stats`)

#### `GET /stats`
Yields tallies and operational counts of threat levels, statuses, and type indicators.
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "Global metrics calculated successfully",
  "data": {
    "total_threats": 35,
    "critical": 2,
    "high": 5,
    "medium": 15,
    "low": 13,
    "open": 10,
    "investigating": 12,
    "contained": 8,
    "closed": 4,
    "false_positive": 1,
    "indicator_type_counts": {
      "ip": 10,
      "domain": 5,
      "hash": 8,
      "url": 12
    },
    "last_updated": "2026-07-01T15:00:00+00:00"
  }
}
```

---

### 3. Vitality Namespace (`/health`)

#### `GET /health`
Returns application live context statistics and database vitality check.
- **Response Payload Example (200 OK)**:
```json
{
  "success": true,
  "message": "System status check executed successfully",
  "data": {
    "application": "healthy",
    "database": "healthy",
    "environment": "development",
    "version": "0.1.0",
    "uptime": 120.45
  }
}
```

---

## Validation & Enums

### Allowed Enums
- **Indicator Types (`indicator_type`)**: `ip`, `domain`, `hash`, `url`
- **Threat Levels (`threat_level`)**: `low`, `medium`, `high`, `critical`
- **Threat Statuses (`status`)**: `Open`, `Investigating`, `Contained`, `Closed`, `False Positive`

### Validation rules
- **Confidence Range**: Must be an integer between `0` and `100` inclusive.
- **State Transition Machine**:
  - `Open ──> Investigating ──> Contained ──> Closed`
  - `Open ──> Investigating ──> False Positive ──> Closed`
  - Re-opening closed records (`Closed` -> `Open`) throws a 400 Validation Error.

---

## Error Handling Specifications

When validation or database errors occur, a standard JSON failure envelope is returned:

```json
{
  "success": false,
  "message": "Validation or structural failure description",
  "errors": [
    "Detailed error description"
  ]
}
```

### HTTP Status Codes
- **400 Bad Request**: Raised when payload validation fails (e.g. out of bound confidence, illegal status change, or malformed JSON).
- **404 Not Found**: Raised when requesting a resource ID that does not exist.
- **405 Method Not Allowed**: Raised when requesting a route with an unsupported HTTP method.
- **500 Internal Server Error**: Raised when database errors or unexpected system exceptions occur.

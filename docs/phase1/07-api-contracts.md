# Phase 1: Credential Vault Foundation
## API Contracts

### 1. Overview
The Vault API routes expose the Credential Vault Foundation capabilities to authorized clients over REST. They rely entirely on the Phase 0 Identity and Policy engines for authentication and authorization.

### 2. Base Path
`/api/v1/vault/secrets`

### 3. Endpoints

#### 3.1 Create Secret
- **Method**: `POST`
- **Path**: `/`
- **Authorization**: `@requires_permission("secrets:write")`
- **Request Body (JSON)**:
  ```json
  {
    "resource_id": "uuid",
    "payload": "string"
  }
  ```
- **Success Response (201 Created)**:
  ```json
  {
    "id": "uuid",
    "resource_id": "uuid",
    "status": "ACTIVE",
    "created_at": "ISO-8601"
  }
  ```
- **Error Responses**:
  - `400 Bad Request` (Invalid payload or resource_id)
  - `401 Unauthorized` (Missing/Invalid Token)
  - `403 Forbidden` (Lacks permission)
  - `409 Conflict` (Resource already has an active secret)

#### 3.2 Retrieve Secret
- **Method**: `GET`
- **Path**: `/{secret_id}/reveal`
- **Authorization**: `@requires_permission("secrets:read")` + Policy Engine Approval Evaluation
- **Success Response (200 OK)**:
  ```json
  {
    "id": "uuid",
    "payload": "string",
    "metadata": {
      "key_version": "string",
      "algorithm": "AES-256-GCM",
      "created_at": "ISO-8601"
    }
  }
  ```
  *(Note: The `payload` field represents the decrypted plaintext transmitted exclusively over TLS. This plaintext is strictly ephemeral, never persisted to disk, and cleared from memory immediately after serialization.)*
- **Error Responses**:
  - `403 Forbidden` (Lacks approval / Access Denied)
  - `404 Not Found` (Secret does not exist or is tombstoned)
  - `503 Service Unavailable` (Master Key unavailable)

#### 3.3 Rotate Secret
- **Method**: `PUT`
- **Path**: `/{secret_id}`
- **Authorization**: `@requires_permission("secrets:write")`
- **Request Body (JSON)**:
  ```json
  {
    "payload": "string"
  }
  ```
- **Success Response (200 OK)**:
  ```json
  {
    "id": "uuid",
    "status": "ACTIVE",
    "updated_at": "ISO-8601"
  }
  ```

#### 3.4 Disable Secret
- **Method**: `DELETE`
- **Path**: `/{secret_id}`
- **Authorization**: `@requires_permission("secrets:delete")`
- **Success Response**: `204 No Content`
- **Error Responses**: `403 Forbidden`, `404 Not Found`

### 4. DTO & Validation Rules
- All requests and responses map to strict Domain Transfer Object (DTO) schemas.
- `payload` fields must explicitly not be logged or cached during serialization or validation mapping.

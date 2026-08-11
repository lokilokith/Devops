# Phase 2 API Design

This document defines the API contracts for the new services introduced in Phase 2. These APIs extend the existing Phase 1 foundation.

## 1. JIT Access APIs

### Request JIT Access
- **Endpoint**: `POST /api/v1/jit-access/request`
- **Method**: `POST`
- **Purpose**: Request temporary, elevated access to a resource.
- **Request Body**:
  ```json
  {
    "resource_id": "uuid",
    "duration_minutes": 60,
    "justification": "Emergency database patch"
  }
  ```
- **Response Format**:
  ```json
  {
    "request_id": "uuid",
    "status": "PENDING_APPROVAL",
    "expires_at": "2026-08-11T20:00:00Z"
  }
  ```
- **Authorization**: Valid User Token

### Approve JIT Access
- **Endpoint**: `POST /api/v1/jit-access/{id}/approve`
- **Method**: `POST`
- **Purpose**: Approve a pending JIT access request.
- **Request Body**:
  ```json
  {
    "decision": "APPROVED",
    "comments": "Approved for 1 hour."
  }
  ```
- **Response Format**:
  ```json
  {
    "request_id": "uuid",
    "status": "APPROVED",
    "session_token": "temporary_jwt"
  }
  ```
- **Authorization**: Approver Role (Manager/Admin)

## 2. Privileged Session APIs

### Start Session
- **Endpoint**: `POST /api/v1/sessions/start`
- **Method**: `POST`
- **Purpose**: Initiate a brokered connection to a resource using a JIT token.
- **Request Body**:
  ```json
  {
    "jit_request_id": "uuid",
    "protocol": "SSH"
  }
  ```
- **Response Format**:
  ```json
  {
    "session_id": "uuid",
    "broker_url": "ssh://broker.opsforge.local:2222",
    "connection_token": "broker_token"
  }
  ```
- **Authorization**: User Token with active JIT approval

### Terminate Session
- **Endpoint**: `POST /api/v1/sessions/{id}/terminate`
- **Method**: `POST`
- **Purpose**: Forcefully terminate an active privileged session.
- **Request Body**: `{}`
- **Response Format**:
  ```json
  {
    "session_id": "uuid",
    "status": "TERMINATED"
  }
  ```
- **Authorization**: Admin Role or Session Owner

## 3. Policy and Vault APIs

### List Dynamic Policies
- **Endpoint**: `GET /api/v1/policies`
- **Method**: `GET`
- **Purpose**: Retrieve a list of ABAC and JIT policies.
- **Request Body**: N/A
- **Response Format**: List of policy objects (name, conditions, max_duration).
- **Authorization**: Admin Role

### Create Rotation Policy
- **Endpoint**: `POST /api/v1/rotation-policies`
- **Method**: `POST`
- **Purpose**: Configure automatic secret rotation for a Vault item.
- **Request Body**:
  ```json
  {
    "vault_item_id": "uuid",
    "interval_seconds": 86400,
    "script_id": "uuid"
  }
  ```
- **Response Format**: Rotation policy configuration object.
- **Authorization**: Admin Role

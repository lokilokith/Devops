# Phase 12 Day 1: Concurrency Model

This document defines the dual-layer concurrency model for the OpsForge SSH Broker.

## The Dual-Layer Architecture

There are two independent concurrency domains involved in broker authorization and session establishment. A failure to distinguish between these domains causes race conditions.

### Domain A — Database Authorization State

The database (PostgreSQL) is the source of truth for all access and authorization logic. The DB state governs the **validity** of a session.

* **Authoritative rows**: `PrivilegedAccessSession`, `JITAccessGrant`, `TargetAccountBinding`.
* **State transitions**: `PENDING` → `ACTIVE`, `ACTIVE` → `TERMINATED`, `ACTIVE` → `REVOKED`.
* **Concurrency mechanism**: Row-level locking via `SELECT ... FOR UPDATE` (using SQLAlchemy's `.with_for_update()`).
* **Critical section**: 
  1. Acquire lock on `PrivilegedAccessSession` and `JITAccessGrant`.
  2. Perform invariant checks (status == ACTIVE/PENDING, now <= expires_at).
  3. Mutate status (PENDING -> ACTIVE).
  4. Commit transaction (releases row locks).
* **Threats mitigated**: Activation vs. Revocation (RACE-02), Activation vs. Expiry (RACE-03).
* **Limitations**: DB locks ONLY protect the DB state. They do not govern process memory or socket attachments.

### Domain B — Broker Process-Local Connection State

The worker process (OpsForgeSSHBroker) is a stateful AsyncIO daemon. It maintains an in-memory registry of active TCP/SSH connections bound to authorized sessions.

* **Authoritative object**: `OpsForgeSSHBroker._active_connections` (Python dict mapping `session_id` -> `asyncssh.SSHServerConnection`).
* **Connection Invariant**: Exactly *one* active SSH connection is allowed per `PrivilegedAccessSession` at any given time. If a duplicate connection arrives for an already-connected session, it MUST be rejected.
* **Concurrency mechanism**: A per-session `asyncio.Lock` managed by a lock registry.
* **Critical section**:
  1. Acquire per-session lock for `session_id`.
  2. Verify DB authorization (Domain A check).
  3. Check `session_id` in `_active_connections`.
  4. If present, REJECT connection.
  5. If absent, REGISTER connection in `_active_connections`.
  6. Release per-session lock.
* **Threats mitigated**: Simultaneous activation (RACE-01), Duplicate session registration (RACE-05).

## Failure Invariants

### 1. DB says ACTIVE, but no connection in Broker
This is safe. It occurs if the client drops the connection or if the broker restarts. The DB session is orphaned. The automated Expiry Monitor (or a future Idle Monitor) will sweep the DB and eventually transition the DB session to `TERMINATED`.

### 2. Connection in Broker, but DB says REVOKED / EXPIRED (Reverse Mismatch)
This is an active threat (Stale Privilege). It is mitigated by the Expiry Monitor background loop, which periodically polls the DB for all `session_id`s in `_active_connections`. If the DB authorization has become invalid (expired, revoked, terminated), the monitor forcefully closes the associated socket, triggering the `connection_lost` handler which cleans up the dictionary.

## Lock Lifecycle

1. **Creation**: When a connection attempts to authorize, the `validate_password` handler fetches or creates an `asyncio.Lock` for the given `session_id` from a global `_session_locks` dictionary.
2. **Contention**: Concurrent callers for the *same* `session_id` will block on `await lock.acquire()`. Callers for different sessions proceed in parallel.
3. **Cleanup**: Locks are reference-counted or eagerly garbage-collected when the connection terminates (`connection_lost`), ensuring no unbounded memory growth.
4. **Separation of Concerns**: The lock state is NOT authorization state. It is strictly an exclusion mechanism for dictionary mutation. DB state remains completely authoritative for authorization.

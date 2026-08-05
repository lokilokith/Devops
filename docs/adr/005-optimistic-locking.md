# ADR 005: Optimistic Concurrency Control
**Status:** Accepted
**Date:** 2026-08-04

## Context
In a distributed deployment, multiple administrators might attempt to rotate or disable the same secret concurrently. Without concurrency controls, this leads to race conditions, orphaned secret versions, and potential data corruption.

## Decision
We will implement optimistic locking on the `Secret` aggregate using a `row_version` integer column.

## Consequences
- **Positive:** Prevents lost updates and guarantees atomic progression of secret versions without expensive or deadlocking database row locks.
- **Negative:** The client or API layer must be prepared to handle HTTP 409 Conflict responses and optionally retry the operation.

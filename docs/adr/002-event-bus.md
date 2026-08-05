# ADR 002: Event Bus for Domain Side-Effects
**Status:** Accepted
**Date:** 2026-08-04

## Context
Vault operations trigger mandatory side effects like Audit logging and Notifications. Direct coupling between the Vault Application Service and Audit Service leads to rigid architectures and potential transaction deadlocks.

## Decision
We will employ an Event Bus pattern. The Vault Application Service will emit domain events (e.g., `SecretCreated`, `SecretAccessed`) containing a `correlation_id` rather than directly invoking downstream consumers.

## Consequences
- **Positive:** Absolute decoupling of bounded contexts, keeping Vault transactions lean.
- **Positive:** Provides a natural extension point for SIEM integration in later phases.
- **Negative:** Asynchronous eventual consistency (Audit events may appear slightly after the HTTP response).

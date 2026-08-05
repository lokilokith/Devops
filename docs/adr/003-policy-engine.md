# ADR 003: Policy-Driven Approval Hooks
**Status:** Accepted
**Date:** 2026-08-04

## Context
Not all secret retrievals mandate identical approval workflows. Forcing a hardcoded approval check within the Vault Domain violates the flexibility required by PAM systems (e.g., some users might need direct access while others require approval).

## Decision
Secret retrieval authorization will be delegated to the Phase 0 Policy Engine. The Vault API will not strictly enforce an Access Request unless the Policy Engine evaluates the request context and mandates it.

## Consequences
- **Positive:** Enables complex organizational rules (e.g., "Break Glass" accounts or permanently authorized admins bypassing approval).
- **Positive:** Vault domain remains agnostic of organization-specific approval rules.
- **Negative:** Increased reliance on the Policy Engine's robustness and accuracy to prevent unauthorized access.

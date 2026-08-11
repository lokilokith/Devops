# Phase 2 Architecture Design

## 1. Phase 2 Vision
The vision for Phase 2 is to elevate OpsForge from a foundational identity and secret management tool into a comprehensive, enterprise-grade Privileged Access Management (PAM) platform. By implementing Just-In-Time (JIT) access, advanced session management, and context-aware policies, OpsForge will enforce the principle of least privilege dynamically and provide deep visibility into all privileged actions.

## 2. System Architecture Diagram
```
User
 | (Requests Access)
Identity & Auth
 | (Verifies Identity)
RBAC / ABAC
 | (Checks Static/Dynamic Rules)
Policy Engine
 | (Evaluates Context: Time, IP, Risk)
Access Request
 | (Initiates JIT Workflow)
Approval Workflow
 | (Multi-tier, Auto-approve logic)
JIT Session (New)
 | (Brokers Connection, Records Session)
Vault
 | (Provides Just-In-Time Credentials)
Audit & Compliance (Enhanced)
```

## 3. New Components
- **JIT Access Service**: Manages the lifecycle of temporary access grants, provisioning and de-provisioning access based on time boundaries.
- **Session Management Service**: Acts as a proxy/broker for privileged connections (e.g., SSH, RDP, DB). Responsible for session recording, live monitoring, and termination.
- **Policy Enhancement Service**: Extends the existing RBAC model to support Attribute-Based Access Control (ABAC), integrating contextual rules.
- **Vault Lifecycle Manager**: Automates secret rotation, manages dynamic secret generation, and monitors secret expiration.
- **Compliance Reporting Service**: Generates structured reports for compliance audits and provides dashboards for security posture.

## 4. Component Interaction
- **Access Flow**: A user requests access to a target system. The `Policy Engine` evaluates the request. If approval is needed, the `Approval Workflow` routes it to approvers. Once approved, the `JIT Access Service` grants temporary privileges.
- **Session Flow**: The user connects via the `Session Management Service`, which retrieves ephemeral credentials from the `Vault`. The session is brokered and recorded.
- **Expiration Flow**: When the time limit is reached, the `JIT Access Service` automatically revokes privileges and terminates active connections via the `Session Management Service`.
- **Audit Flow**: Every step, from request to session termination and keystrokes (if recorded), is logged immutably into the `Audit` component.

## 5. Security Boundaries
- **Broker Isolation**: The Session Management Service acts as an isolated broker; users never see the actual credentials for target resources.
- **Ephemeral Credentials**: Vault issues short-lived credentials that become invalid immediately after the session or time window expires.
- **Immutable Audit**: All JIT requests, approvals, and session logs are cryptographically sealed to prevent tampering.

## 6. Deployment Impact
- Requires scalable storage for session recordings (e.g., S3 or Blob Storage).
- Session Management Service will require network proximity and firewall access to target resources.
- Background workers (Celery/Redis) will need to be scaled to handle automated rotation and JIT expiration jobs.

## 7. Backward Compatibility with Phase 1
- The existing RBAC model will be preserved. Phase 2 ABAC and JIT policies will sit on top of the Phase 1 RBAC foundation.
- Existing static permissions will continue to function unless migrated to JIT policies.
- Vault APIs remain compatible; new endpoints will be added for rotation policies.

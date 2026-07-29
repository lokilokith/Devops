# RBAC Permission Matrix

This document defines the default System Roles and the permissions each role is intended to have within OpsForge.

| Role                   | Users            | Roles | Permissions | Resources |
| ---------------------- | ---------------- | ----- | ----------- | --------- |
| Administrator          | CRUD             | CRUD  | CRUD        | CRUD      |
| Security Administrator | CRUD             | Read  | CRUD        | Read      |
| SOC Analyst            | Read             | None  | Read        | Read      |
| Auditor                | Read             | Read  | Read        | Read      |
| Help Desk              | Update (limited) | None  | None        | None      |

## Definitions
- **Administrator**: Full platform access.
- **Security Administrator**: Manages users and permissions, read-only on roles and resources.
- **SOC Analyst**: Read-only access to users, permissions, and resources.
- **Auditor**: Broad read-only access for compliance and verification.
- **Help Desk**: Limited user update capabilities (e.g. password resets, status changes).

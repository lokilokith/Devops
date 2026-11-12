# Security Model & RBAC

OpsForge uses a strict, centralized Role-Based Access Control (RBAC) model. All access and mutations in the system are governed by explicit permissions.

## Authentication
- Users authenticate via JWT (JSON Web Tokens).
- Tokens must be transmitted via the Authorization: Bearer <token> header.

## Authorization & RBAC
Permissions are defined as a matrix of \Resources\ and \Roles\.
1. **Roles**: Groupings of permissions (e.g., ADMIN, SOC_ANALYST).
2. **Permissions**: Specific actions on resources (e.g., CREATE_USER, VIEW_REPORTS).

### Role Bootstrapping
On startup, bac_seed_service.py ensures the default secure RBAC matrix is loaded and verified. If the database is missing core roles (like ADMIN), the bootstrap process prevents the application from starting in an insecure state.

## Hardening
- **SAST**: Bandit is executed in the CI/CD pipeline to detect unsafe Python patterns.
- **SCA**: pip-audit and Safety check dependencies for known vulnerabilities.

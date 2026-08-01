"""Default System Roles definition for OpsForge RBAC."""

DEFAULT_ROLES = [
    {
        "role_code": "ADMIN",
        "role_name": "Administrator",
        "description": "Full platform access.",
    },
    {
        "role_code": "SEC_ADMIN",
        "role_name": "Security Administrator",
        "description": "Manages users and permissions, read-only on roles and resources.",
    },
    {
        "role_code": "SOC_ANALYST",
        "role_name": "SOC Analyst",
        "description": "Read-only access to users, permissions, and resources.",
    },
    {
        "role_code": "AUDITOR",
        "role_name": "Auditor",
        "description": "Broad read-only access for compliance and verification.",
    },
    {
        "role_code": "HELP_DESK",
        "role_name": "Help Desk",
        "description": "Limited user update capabilities (e.g. password resets, status changes).",
    },
]

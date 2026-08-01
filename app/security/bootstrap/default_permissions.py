"""Default Permissions definition for OpsForge RBAC."""

DEFAULT_PERMISSIONS = [
    # Users
    ("users", "read"),
    ("users", "create"),
    ("users", "update"),
    ("users", "delete"),
    # Roles
    ("roles", "read"),
    ("roles", "create"),
    ("roles", "update"),
    ("roles", "delete"),
    # Permissions
    ("permissions", "read"),
    ("permissions", "create"),
    ("permissions", "update"),
    ("permissions", "delete"),
    # Resources
    ("resources", "read"),
    ("resources", "create"),
    ("resources", "update"),
    ("resources", "delete"),
    # Management associations
    ("user_roles", "manage"),
    ("role_permissions", "manage"),
    # Access Requests
    ("access_requests", "create"),
    ("access_requests", "read"),
    ("access_requests", "approve"),
    ("access_requests", "reject"),
    ("access_requests", "cancel"),
    # Approval Workflows
    ("approval_workflows", "read"),
    ("approval_workflows", "approve"),
    ("approval_workflows", "reject"),
    ("approval_workflows", "cancel"),
    ("approval_workflows", "override"),
    ("approval_workflows", "escalate"),
    # Notifications
    ("notifications", "read"),
    ("notifications", "update"),
    ("notifications", "delete"),
]

ROLE_PERMISSION_MAP = {
    "ADMIN": ["*"],
    "SEC_ADMIN": [
        "PERM_USERS_READ",
        "PERM_USERS_CREATE",
        "PERM_USERS_UPDATE",
        "PERM_USERS_DELETE",
        "PERM_ROLES_READ",
        "PERM_PERMISSIONS_READ",
        "PERM_RESOURCES_READ",
        "PERM_USER_ROLES_MANAGE",
        "PERM_ROLE_PERMISSIONS_MANAGE",
    ],
    "SOC_ANALYST": [
        "PERM_USERS_READ",
        "PERM_ROLES_READ",
        "PERM_PERMISSIONS_READ",
        "PERM_RESOURCES_READ",
        "PERM_ACCESS_REQUESTS_READ",
        "PERM_APPROVAL_WORKFLOWS_READ",
        "PERM_NOTIFICATIONS_READ",
    ],
    "AUDITOR": [
        "PERM_USERS_READ",
        "PERM_ROLES_READ",
        "PERM_PERMISSIONS_READ",
        "PERM_RESOURCES_READ",
        "PERM_ACCESS_REQUESTS_READ",
        "PERM_APPROVAL_WORKFLOWS_READ",
        "PERM_NOTIFICATIONS_READ",
    ],
    "HELP_DESK": [
        "PERM_USERS_READ",
        "PERM_USERS_UPDATE",
        "PERM_ACCESS_REQUESTS_READ",
        "PERM_ACCESS_REQUESTS_CREATE",
        "PERM_ACCESS_REQUESTS_CANCEL",
        "PERM_NOTIFICATIONS_READ",
        "PERM_NOTIFICATIONS_UPDATE",
    ],
}

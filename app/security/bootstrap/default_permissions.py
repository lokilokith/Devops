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

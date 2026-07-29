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
]

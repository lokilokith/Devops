"""Default Resources definition for OpsForge RBAC."""

DEFAULT_RESOURCES = [
    {
        "resource_code": "RESOURCE_USERS",
        "resource_name": "User Management",
        "description": "User accounts and identities."
    },
    {
        "resource_code": "RESOURCE_ROLES",
        "resource_name": "Role Management",
        "description": "System and custom roles."
    },
    {
        "resource_code": "RESOURCE_PERMISSIONS",
        "resource_name": "Permission Management",
        "description": "Granular authorization rights."
    },
    {
        "resource_code": "RESOURCE_RESOURCES",
        "resource_name": "Resource Management",
        "description": "Platform infrastructure and logical assets."
    },
    {
        "resource_code": "RESOURCE_USER_ROLES",
        "resource_name": "User Role Management",
        "description": "Assignments between users and roles."
    },
    {
        "resource_code": "RESOURCE_ROLE_PERMISSIONS",
        "resource_name": "Role Permission Management",
        "description": "Assignments between roles and permissions."
    }
]

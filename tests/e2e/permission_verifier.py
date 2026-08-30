import psycopg2


def main():
    conn = psycopg2.connect(
        "postgresql://opsforge:opsforge_pass@opsforge-postgres/opsforge_db"
    )
    cur = conn.cursor()

    print("Checking Permissions...")
    cur.execute("SELECT permission_code FROM permissions")
    permissions = [row[0] for row in cur.fetchall()]  # noqa: F841

    expected_perms = [
        "PERM_USERS_READ",
        "PERM_USERS_CREATE",
        "PERM_USERS_UPDATE",
        "PERM_USERS_DELETE",
        "PERM_ROLES_READ",
        "PERM_ROLES_CREATE",
        "PERM_ROLES_UPDATE",
        "PERM_ROLES_DELETE",
        "PERM_PERMISSIONS_READ",
        "PERM_PERMISSIONS_CREATE",
        "PERM_PERMISSIONS_UPDATE",
        "PERM_PERMISSIONS_DELETE",
        "PERM_RESOURCES_READ",
        "PERM_RESOURCES_CREATE",
        "PERM_RESOURCES_UPDATE",
        "PERM_RESOURCES_DELETE",
        "PERM_USER_ROLES_MANAGE",
        "PERM_ROLE_PERMISSIONS_MANAGE",
        "PERM_ACCESS_REQUESTS_READ",
        "PERM_ACCESS_REQUESTS_CREATE",
        "PERM_ACCESS_REQUESTS_APPROVE",
        "PERM_ACCESS_REQUESTS_REJECT",
        "PERM_ACCESS_REQUESTS_CANCEL",
        "PERM_APPROVAL_WORKFLOWS_READ",
        "PERM_APPROVAL_WORKFLOWS_APPROVE",
        "PERM_APPROVAL_WORKFLOWS_REJECT",
        "PERM_APPROVAL_WORKFLOWS_CANCEL",
        "PERM_APPROVAL_WORKFLOWS_OVERRIDE",
        "PERM_APPROVAL_WORKFLOWS_ESCALATE",
        "PERM_NOTIFICATIONS_READ",
        "PERM_NOTIFICATIONS_UPDATE",
        "PERM_NOTIFICATIONS_DELETE",
        "PERM_VAULT_READ",
        "PERM_VAULT_CREATE",
        "PERM_VAULT_UPDATE",
        "PERM_VAULT_DELETE",
    ]

    # Check role to permission mappings
    print("Checking Role mappings...")
    roles_expected = {
        "ADMIN": expected_perms,
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
            "PERM_ACCESS_REQUESTS_CREATE",
            "PERM_ACCESS_REQUESTS_READ",
            "PERM_ACCESS_REQUESTS_CANCEL",
            "PERM_NOTIFICATIONS_READ",
            "PERM_NOTIFICATIONS_UPDATE",
        ],
    }

    for role_code, perms in roles_expected.items():
        cur.execute(
            f"SELECT p.permission_code FROM permissions p JOIN role_permissions rp ON p.id = rp.permission_id JOIN roles r ON rp.role_id = r.id WHERE r.role_code = '{role_code}'"
        )
        actual_perms = [row[0] for row in cur.fetchall()]
        for p in perms:
            assert p in actual_perms, f"Role {role_code} missing permission: {p}"

    print("Permissions check passed.")


if __name__ == "__main__":
    main()

import sys

# Roles Service
with open('app/roles/service.py', 'r') as f:
    content = f.read()
content = content.replace("self._repository.search_roles(", "self._repository.search(role_code=")
content = content.replace("self._repository.list_roles(", "self._repository.list(offset=")
content = content.replace("self._repository.count_roles(", "self._repository.count(")
content = content.replace("except RoleRepositoryError", "except RolesRepositoryError")
with open('app/roles/service.py', 'w') as f:
    f.write(content)

# Roles Repository
with open('app/roles/repository.py', 'r') as f:
    content = f.read()
content = content.replace("RoleRepositoryError", "RolesRepositoryError")
with open('app/roles/repository.py', 'w') as f:
    f.write(content)

# Permissions Service
with open('app/permissions/service.py', 'r') as f:
    content = f.read()
content = content.replace("self._repository.search_permissions(", "self._repository.search(permission_code=")
content = content.replace("self._repository.list_permissions(", "self._repository.list(offset=")
content = content.replace("self._repository.count_permissions(", "self._repository.count(")
content = content.replace("except PermissionRepositoryError", "except PermissionsRepositoryError")
with open('app/permissions/service.py', 'w') as f:
    f.write(content)

# Permissions Repository
with open('app/permissions/repository.py', 'r') as f:
    content = f.read()
content = content.replace("PermissionRepositoryError", "PermissionsRepositoryError")
with open('app/permissions/repository.py', 'w') as f:
    f.write(content)

print("Fixed")

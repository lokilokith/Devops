import sys

with open('app/roles/repository.py', 'r') as f:
    content = f.read()

func = '''
    def search_roles(self, query: str, offset: int = 0, limit: int = 100) -> Sequence[Role]:
        try:
            from sqlalchemy import or_
            bounded_limit, normalized_offset = self._normalize_pagination(limit, offset)
            pattern = f"%{query}%"
            stmt = select(Role).where(or_(
                Role.role_code.ilike(pattern),
                Role.role_name.ilike(pattern)
            )).order_by(Role.created_at.desc()).offset(normalized_offset).limit(bounded_limit)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError("Failed to search roles.") from err
'''
if "def search_roles" not in content:
    content = content.replace("__all__ = [", func + "\n__all__ = [")
with open('app/roles/repository.py', 'w') as f:
    f.write(content)

with open('app/roles/service.py', 'r') as f:
    content = f.read()
content = content.replace(
    "roles = self._repository.search(role_name=search, offset=skip, limit=limit)",
    "roles = self._repository.search_roles(search, offset=skip, limit=limit)"
)
with open('app/roles/service.py', 'w') as f:
    f.write(content)


with open('app/permissions/repository.py', 'r') as f:
    content = f.read()

func = '''
    def search_permissions(self, query: str, offset: int = 0, limit: int = 100) -> Sequence[Permission]:
        try:
            from sqlalchemy import or_
            bounded_limit, normalized_offset = self._normalize_pagination(limit, offset)
            pattern = f"%{query}%"
            stmt = select(Permission).where(or_(
                Permission.permission_code.ilike(pattern),
                Permission.permission_name.ilike(pattern)
            )).order_by(Permission.created_at.desc()).offset(normalized_offset).limit(bounded_limit)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError("Failed to search permissions.") from err
'''
if "def search_permissions" not in content:
    content = content.replace("__all__ = [", func + "\n__all__ = [")
with open('app/permissions/repository.py', 'w') as f:
    f.write(content)

with open('app/permissions/service.py', 'r') as f:
    content = f.read()
content = content.replace(
    "perms = self._repository.search(permission_name=search, offset=skip, limit=limit)",
    "perms = self._repository.search_permissions(search, offset=skip, limit=limit)"
)
with open('app/permissions/service.py', 'w') as f:
    f.write(content)

print("Fixed search methods")

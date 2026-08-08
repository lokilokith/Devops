import sys

# 1. Fix Roles Search and Pagination
def fix_roles():
    # Service
    with open('app/roles/service.py', 'r') as f:
        content = f.read()
    content = content.replace(
        "def list_roles(self, skip: int = 0, limit: int = 100) -> Sequence[Role]:",
        "def list_roles(self, skip: int = 0, limit: int = 100, search: str = '') -> tuple[Sequence[Role], int]:"
    )
    body = '''        try:
            if search:
                roles = self._repository.search_roles(search, skip=skip, limit=limit)
                total = self._repository.count_search_roles(search)
                return roles, total
            else:
                roles = self._repository.list_roles(skip=skip, limit=limit)
                total = self._repository.count_roles()
                return roles, total
        except RoleRepositoryError as e:'''
    content = content.replace(
'''        try:
            return self._repository.list_roles(skip=skip, limit=limit)
        except RoleRepositoryError as e:''', body)
    with open('app/roles/service.py', 'w') as f:
        f.write(content)

    # Repository
    with open('app/roles/repository.py', 'r') as f:
        content = f.read()
    if "def count_search_roles" not in content:
        func = '''
    def count_search_roles(self, query: str) -> int:
        try:
            from sqlalchemy import func, or_
            pattern = f"%{query}%"
            stmt = select(func.count()).select_from(Role).where(or_(
                Role.role_code.ilike(pattern),
                Role.role_name.ilike(pattern)
            ))
            return self._session.scalar(stmt) or 0
        except SQLAlchemyError as err:
            raise RoleRepositoryError("Failed to count searched roles.") from err
'''
        # insert before __all__
        content = content.replace("__all__ = [", func + "\n__all__ = [")
    with open('app/roles/repository.py', 'w') as f:
        f.write(content)

    # Routes
    with open('app/roles/routes.py', 'r') as f:
        content = f.read()
    content = content.replace(
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        service = get_service()
        roles = service.list_roles(skip=skip, limit=limit)
        return success_response(data=roles)''',
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        search = request.args.get("search", "")
        service = get_service()
        roles, total = service.list_roles(skip=skip, limit=limit, search=search)
        return success_response(data=roles, meta={"total": total, "skip": skip, "limit": limit})'''
    )
    with open('app/roles/routes.py', 'w') as f:
        f.write(content)

# 2. Fix Permissions Search and Pagination
def fix_permissions():
    # Service
    with open('app/permissions/service.py', 'r') as f:
        content = f.read()
    content = content.replace(
        "def list_permissions(self, skip: int = 0, limit: int = 100) -> Sequence[Permission]:",
        "def list_permissions(self, skip: int = 0, limit: int = 100, search: str = '') -> tuple[Sequence[Permission], int]:"
    )
    body = '''        try:
            if search:
                perms = self._repository.search_permissions(search, skip=skip, limit=limit)
                total = self._repository.count_search_permissions(search)
                return perms, total
            else:
                perms = self._repository.list_permissions(skip=skip, limit=limit)
                total = self._repository.count_permissions()
                return perms, total
        except PermissionRepositoryError as e:'''
    content = content.replace(
'''        try:
            return self._repository.list_permissions(skip=skip, limit=limit)
        except PermissionRepositoryError as e:''', body)
    with open('app/permissions/service.py', 'w') as f:
        f.write(content)

    # Repository
    with open('app/permissions/repository.py', 'r') as f:
        content = f.read()
    if "def count_search_permissions" not in content:
        func = '''
    def count_search_permissions(self, query: str) -> int:
        try:
            from sqlalchemy import func, or_
            pattern = f"%{query}%"
            stmt = select(func.count()).select_from(Permission).where(or_(
                Permission.permission_code.ilike(pattern),
                Permission.permission_name.ilike(pattern)
            ))
            return self._session.scalar(stmt) or 0
        except SQLAlchemyError as err:
            raise PermissionRepositoryError("Failed to count searched permissions.") from err
'''
        content = content.replace("__all__ = [", func + "\n__all__ = [")
    with open('app/permissions/repository.py', 'w') as f:
        f.write(content)

    # Routes
    with open('app/permissions/routes.py', 'r') as f:
        content = f.read()
    content = content.replace(
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        service = get_service()
        permissions = service.list_permissions(skip=skip, limit=limit)
        return success_response(data=permissions)''',
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        search = request.args.get("search", "")
        service = get_service()
        permissions, total = service.list_permissions(skip=skip, limit=limit, search=search)
        return success_response(data=permissions, meta={"total": total, "skip": skip, "limit": limit})'''
    )
    with open('app/permissions/routes.py', 'w') as f:
        f.write(content)

fix_roles()
fix_permissions()
print("Done")

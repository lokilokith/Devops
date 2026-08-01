import sys

def modify_service():
    with open('app/identity/service.py', 'r') as f:
        content = f.read()
    
    # modify list_users to take search and return both users and total
    content = content.replace(
        "def list_users(self, skip: int = 0, limit: int = 100) -> Sequence[User]:",
        "def list_users(self, skip: int = 0, limit: int = 100, search: str = '') -> tuple[Sequence[User], int]:"
    )
    
    body = '''        try:
            if search:
                users = self._repository.search_users(search, skip=skip, limit=limit)
                total = self._repository.count_search_users(search)
                return users, total
            else:
                users = self._repository.list_users(skip=skip, limit=limit)
                total = self._repository.count_users()
                return users, total
        except IdentityRepositoryError as e:'''
        
    content = content.replace(
'''        try:
            return self._repository.list_users(skip=skip, limit=limit)
        except IdentityRepositoryError as e:''',
        body
    )
    
    with open('app/identity/service.py', 'w') as f:
        f.write(content)


def modify_repo():
    with open('app/identity/repository.py', 'r') as f:
        content = f.read()
        
    if "def count_search_users" not in content:
        func = '''
    def count_search_users(self, query: str) -> int:
        try:
            from sqlalchemy import func, or_
            pattern = f"%{query}%"
            stmt = select(func.count()).select_from(User).where(or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.employee_id.ilike(pattern),
                User.full_name.ilike(pattern)
            ))
            return self._session.scalar(stmt) or 0
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to count searched users.") from err
'''
        content += func
        with open('app/identity/repository.py', 'w') as f:
            f.write(content)

def modify_routes():
    with open('app/identity/routes.py', 'r') as f:
        content = f.read()
        
    content = content.replace(
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        service = get_service()
        users = service.list_users(skip=skip, limit=limit)
        return success_response(data=users)''',
        '''        skip, limit = validate_pagination(request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE))
        search = request.args.get("search", "")
        service = get_service()
        users, total = service.list_users(skip=skip, limit=limit, search=search)
        return success_response(data=users, meta={"total": total, "skip": skip, "limit": limit})'''
    )
    with open('app/identity/routes.py', 'w') as f:
        f.write(content)


modify_service()
modify_repo()
modify_routes()
print("Done")

import os

def fix_file(filepath, module_name, repo_name):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Add import for repo
        import_stmt = f"from app.{module_name}.repository import {repo_name}"
        if import_stmt not in content:
            content = content.replace(f"from app.{module_name}.service import", f"{import_stmt}\nfrom app.{module_name}.service import")
            
        # Fix get_service
        content = content.replace(f"Service(db.session)", f"Service({repo_name}(db.session))")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")

fix_file('l:/DOWNLOADS/Devops/opsforge/app/roles/routes.py', 'roles', 'RolesRepository')
fix_file('l:/DOWNLOADS/Devops/opsforge/app/permissions/routes.py', 'permissions', 'PermissionsRepository')
fix_file('l:/DOWNLOADS/Devops/opsforge/app/resources/routes.py', 'resources', 'ResourcesRepository')


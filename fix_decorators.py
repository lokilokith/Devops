import os
import glob
import re

mapping = {
    '"IDENTITY"': '"users"',
    '"ROLE"': '"roles"',
    '"PERMISSION"': '"permissions"',
    '"RESOURCE"': '"resources"',
    '"ROLE_PERMISSION"': '"role_permissions"',
    '"USER_ROLE"': '"user_roles"'
}

for filepath in glob.glob('l:/DOWNLOADS/Devops/opsforge/app/**/*.py', recursive=True):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = content
    for old, new in mapping.items():
        modified = modified.replace(old, new)
        
    if modified != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(modified)
        print(f"Updated {filepath}")

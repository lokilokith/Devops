import ast
import os
import sys

def get_imports(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except Exception:
            return set()
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def main():
    root_dirs = ['app', 'tests']
    all_imports = set()
    for root_dir in root_dirs:
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename.endswith('.py'):
                    all_imports.update(get_imports(os.path.join(dirpath, filename)))
    
    # Python 3.11 stdlib list approximation (and some common ones)
    stdlib = {
        'os', 'sys', 'time', 'datetime', 'json', 're', 'uuid', 'functools', 'collections',
        'typing', 'logging', 'argparse', 'math', 'random', 'itertools', 'traceback', 'hashlib',
        'hmac', 'base64', 'urllib', 'multiprocessing', 'concurrent', 'asyncio', 'tempfile',
        'shutil', 'subprocess', 'pathlib', 'enum', 'inspect', 'warnings', 'contextlib', 'unittest',
        'io', 'dataclasses'
    }
    
    internal = {'app', 'tests', 'conftest'}
    
    external = all_imports - stdlib - internal
    print("External Imports:")
    for imp in sorted(list(external)):
        print(imp)

if __name__ == '__main__':
    main()

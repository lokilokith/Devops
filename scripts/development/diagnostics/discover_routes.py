import ast
import os
import glob

def find_routes():
    app_dir = os.path.join(os.path.dirname(__file__), '..', 'app')
    route_files = glob.glob(os.path.join(app_dir, '**', 'routes.py'), recursive=True)
    
    endpoints = []
    
    for rf in route_files:
        with open(rf, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
            
        module_name = os.path.relpath(rf, app_dir).replace(os.sep, '.')[:-3]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                perms = []
                is_login_required = False
                
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == 'login_required':
                        is_login_required = True
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name) and dec.func.id == 'requires_permission':
                            try:
                                args = [arg.value for arg in dec.args if isinstance(arg, ast.Constant)]
                                if len(args) == 2:
                                    perms.append(f"{args[0]}.{args[1]}")
                            except Exception:
                                pass
                if perms or is_login_required:
                    endpoints.append({
                        "file": module_name,
                        "function": node.name,
                        "permissions": perms,
                        "login_required": is_login_required
                    })
    
    for ep in endpoints:
        print(ep)

if __name__ == "__main__":
    find_routes()
